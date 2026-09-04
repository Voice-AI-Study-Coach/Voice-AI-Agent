import os
import sys
import time
import threading
import itertools

from dotenv import load_dotenv

from src.exception import CustomException
from src.logger import logging

load_dotenv()

# Default cooldown applied when a provider returns a rate-limit error
# without telling us how long to wait (e.g. no Retry-After header).
DEFAULT_COOLDOWN_SECONDS = 60


def _load_numbered_keys(prefix: str) -> list[str]:
    """Load KEY_1, KEY_2, ... env vars for a given prefix, in order."""
    keys = []
    for i in itertools.count(1):
        val = os.getenv(f"{prefix}_{i}")
        if val is None:
            break
        keys.append(val)
    if not keys:
        # fall back to a single unnumbered var, e.g. GROQ_API_KEY
        single = os.getenv(prefix)
        if single:
            keys.append(single)
    return keys


class KeyPool:
    """
    Tracks a set of API keys for one provider and hands out whichever
    key is currently NOT rate-limited. Thread-safe.

    Usage:
        pool = KeyPool("GROQ_API_KEY")
        key = pool.get_key()          # raises if all keys are cooling down
        ... use key for a request ...
        pool.mark_rate_limited(key)   # call this when the request gets a 429
    """

    def __init__(self, prefix: str, cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS):
        self.prefix = prefix
        self.cooldown_seconds = cooldown_seconds
        self._keys = _load_numbered_keys(prefix)
        if not self._keys:
            raise CustomException(
                f"No API keys found for prefix '{prefix}' in environment", sys
            )
        self._lock = threading.Lock()
        # cooldown_until[key] = unix timestamp when key becomes available again
        self._cooldown_until = {k: 0.0 for k in self._keys}
        self._rr = itertools.cycle(range(len(self._keys)))

    def _is_available(self, key: str) -> bool:
        return time.time() >= self._cooldown_until[key]

    def status(self) -> dict:
        """Snapshot of every key's availability, for monitoring/logging."""
        now = time.time()
        return {
            self._mask(k): (
                "available" if now >= until else f"cooling_down ({until - now:.0f}s left)"
            )
            for k, until in self._cooldown_until.items()
        }

    @staticmethod
    def _mask(key: str) -> str:
        return f"{key[:6]}...{key[-4:]}" if len(key) > 10 else "***"

    def get_key(self, wait: bool = True) -> str:
        """
        Return the next available (not rate-limited) key, round-robin.
        If all keys are cooling down:
          - wait=True: sleep until the soonest key frees up, then return it.
          - wait=False: raise CustomException.
        """
        try:
            with self._lock:
                n = len(self._keys)
                for _ in range(n):
                    idx = next(self._rr)
                    key = self._keys[idx]
                    if self._is_available(key):
                        return key

                # all keys are cooling down
                soonest_key = min(self._cooldown_until, key=self._cooldown_until.get)
                wait_for = self._cooldown_until[soonest_key] - time.time()

            if not wait or wait_for <= 0:
                if wait_for <= 0:
                    return soonest_key
                raise CustomException(
                    f"All {self.prefix} keys are rate-limited "
                    f"(soonest free in {wait_for:.0f}s)",
                    sys,
                )

            logging.info(
                f"All {self.prefix} keys rate-limited; waiting {wait_for:.0f}s "
                f"for {self._mask(soonest_key)}"
            )
            time.sleep(wait_for)
            return soonest_key
        except CustomException:
            raise
        except Exception as e:
            raise CustomException(e, sys)

    def mark_rate_limited(self, key: str, retry_after: float | None = None):
        """Cool a key down after it gets a 429 / rate-limit error."""
        cooldown = retry_after if retry_after is not None else self.cooldown_seconds
        with self._lock:
            self._cooldown_until[key] = time.time() + cooldown
        logging.info(f"{self.prefix} key {self._mask(key)} rate-limited, "
                      f"cooling down for {cooldown:.0f}s")

    def mark_success(self, key: str):
        """Optional: explicitly clear any cooldown on a successful call."""
        with self._lock:
            self._cooldown_until[key] = 0.0


# Shared pools for the providers this project uses.
groq_pool = KeyPool("GROQ_API_KEY")
gemini_pool = KeyPool("GEMINI_API_KEY")
mistral_pool = KeyPool("MISTRAL_API_KEY", cooldown_seconds=5)
deepgram_pool = KeyPool("DEEPGRAM_API_KEY")


def is_rate_limit_error(exc: Exception) -> bool:
    """Best-effort detection of a 429 / rate-limit error from Groq or Gemini SDKs."""
    msg = str(exc).lower()
    status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    return status_code == 429 or "429" in msg or "rate limit" in msg or "resource_exhausted" in msg


def is_transient_tool_error(exc: Exception) -> bool:
    """
    Best-effort detection of a transient tool-calling glitch (e.g. Groq's
    'tool_use_failed' when the model mis-frames a large/short-field JSON
    payload). Worth a retry, unlike a genuine schema/logic error.
    """
    msg = str(exc).lower()
    return "tool_use_failed" in msg or "failed to call a function" in msg
