import os
import sys
import threading
import time
import jwt

from src.exception import CustomException
from dotenv import load_dotenv
from fastapi import HTTPException
from fastapi.requests import Request
from fastapi.websockets import WebSocket
from backend.db import fetch_one

# The users row is re-checked at most this often per user.
#
# Every authenticated request used to pay a round trip to Neon (~0.5s warm)
# just to confirm the token's user still exists - on top of whatever the
# endpoint itself queried. The token already carries user_id, name and email,
# and it is signed, so those values need no lookup to be trusted; the query
# exists only so that deleting a user invalidates their still-valid 30-day
# token. Caching the existence check keeps that property while taking the
# round trip off the hot path: a deleted user is locked out within this
# window rather than instantly, which is the right trade for a check that
# was costing every request in the app.
USER_CACHE_TTL_SECONDS = 60

# user_id -> (row, checked_at). Guarded by a lock because FastAPI runs sync
# handlers across a threadpool, so several requests can miss at once.
_user_cache: dict[int, tuple[dict, float]] = {}
_user_cache_lock = threading.Lock()


def invalidate_user_cache(user_id: int | None = None) -> None:
    """Drop cached existence checks - one user, or all of them.

    Call after deleting a user so their token stops working immediately
    rather than at the end of the TTL window."""
    with _user_cache_lock:
        if user_id is None:
            _user_cache.clear()
        else:
            _user_cache.pop(user_id, None)


def _resolve_user(token: str | None) -> dict:
    """Shared core of verify_jwt: decode the token and confirm the user
    still exists. Raises HTTPException(401) on any failure - both the HTTP
    and WebSocket callers below translate that the same way, just through
    different transports (a response vs. a close code)."""
    if not token:
        raise HTTPException(status_code=401, detail="Missing access token")
    try:
        decoded = jwt.decode(token, os.environ.get("JWT_SECRET_KEY"), algorithms=["HS256"])
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired access token")

    user_id = decoded["user_id"]
    now = time.monotonic()

    with _user_cache_lock:
        hit = _user_cache.get(user_id)
        if hit is not None and now - hit[1] < USER_CACHE_TTL_SECONDS:
            return hit[0]

    # Deliberately outside the lock: this is the slow network call, and
    # holding the lock across it would serialise every authenticated request
    # in the process behind one round trip. A concurrent duplicate fetch for
    # the same user is cheap and self-correcting.
    user = fetch_one(
        "select user_id, name, email from users where user_id = %s",
        (user_id,),
    )
    if not user:
        # A missing row must not stay cached as a negative, or a freshly
        # created user could be locked out - just drop any stale entry.
        invalidate_user_cache(user_id)
        raise HTTPException(status_code=401, detail="Invalid access token")

    with _user_cache_lock:
        _user_cache[user_id] = (user, now)
    return user


def verify_jwt(request: Request):
    try:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.removeprefix("Bearer ").strip()
        else:
            token = request.cookies.get("access_token")
        request.state.user = _resolve_user(token)
    except HTTPException:
        raise
    except Exception as e:
        raise CustomException(e, sys)


async def verify_jwt_ws(websocket: WebSocket) -> dict:
    """WebSocket equivalent of verify_jwt.

    Not usable as a FastAPI `Depends` on a WebSocket route the way verify_jwt
    is on HTTP ones - a WebSocket connection is not a Request, and by the
    time a route body runs the handshake has already been accepted. Callers
    must call this explicitly, before `websocket.accept()`, and close the
    connection themselves if it raises.

    The access_token cookie rides along on the WebSocket handshake the same
    way it does on a normal HTTP request, so no separate auth message from
    the client is needed for the common case.
    """
    try:
        auth_header = websocket.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.removeprefix("Bearer ").strip()
        else:
            token = websocket.cookies.get("access_token")
        return _resolve_user(token)
    except HTTPException:
        raise
    except Exception as e:
        raise CustomException(e, sys)
