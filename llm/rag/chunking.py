import os
import sys
import re

from concurrent.futures import ThreadPoolExecutor

from langchain_ollama import ChatOllama
from langchain_mistralai import ChatMistralAI
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from src.exception import CustomException
from src.logger import logging
from llm.schemas import Sections
from llm.prompts import chunking_prompt
from llm.rotation_shifting import mistral_pool, is_rate_limit_error
from dotenv import load_dotenv
from langchain_classic.output_parsers import PydanticOutputParser

load_dotenv()

import time

# How many chunking windows are in flight at once. Concurrency is kept modest (2)
# to prevent bursting account-level RPM quotas on Mistral's API.
CHUNK_CONCURRENCY = 2


class Chunking:
    def __init__(self, doc, toc):
        self.doc = doc
        self.toc = toc

    def _structured_mistral(self):
        """Build a ChatMistralAI structured-output client using a key that isn't rate-limited."""
        key = mistral_pool.get_key()
        llm = ChatMistralAI(model="open-mistral-7b", temperature=0, api_key=key)
        return key, llm.with_structured_output(schema=Sections)

    def _invoke_with_rotation(self, prompt):
        """Invoke Mistral with key rotation, request pacing, and jittered backoff."""
        last_exc = None
        for attempt in range(3):
            for _ in range(len(mistral_pool._keys)):
                key, structured = self._structured_mistral()
                try:
                    result = structured.invoke(prompt)
                    mistral_pool.mark_success(key)
                    return result
                except Exception as e:
                    if is_rate_limit_error(e):
                        mistral_pool.mark_rate_limited(key)
                        last_exc = e
                        time.sleep(0.3)  # brief stagger before picking next key
                        continue
                    raise
            time.sleep(2.0)  # pause briefly before next pass if all keys are cooling down
        raise CustomException(last_exc or "All Mistral keys are rate-limited", sys)

    def _sections_for(self, prompt):
        """One window's sections. Separate method so it can be mapped over a
        thread pool; the key rotation inside is already per-call and
        thread-safe (KeyPool guards its own state with a lock)."""
        return self._invoke_with_rotation(prompt).sections

    def documentChunking(self):
        try:
            full, page_starts = "", []
            for p in range(self.doc.page_count):
                page_starts.append(len(full))
                full += self.doc[p].get_text()

            hints = []
            for level, title, page in self.toc:
                clean = re.sub(r'\s*\(\d+\)$', '', title).strip()
                if len(clean) > 3 and re.search(r'[A-Za-z]{3,}', clean):
                    hints.append(clean)
            lines = full.split("\n")
            WINDOW = 150

            prompts = []
            for start in range(0, len(lines), WINDOW):
                window = lines[start:start + WINDOW]
                numbered_w = "\n".join(f"{start+i}: {l}" for i, l in enumerate(window))
                prompts.append(chunking_prompt(hints=hints, numbered_w=numbered_w))

            # One LLM call per window, run CONCURRENTLY. The windows are
            # independent - each is told its own absolute line numbers, and the
            # sections come back sorted by start_line below - so the order they
            # finish in does not matter. Run serially this was the slowest part
            # of ingestion by far: a 3000-line PDF is 20 windows, each a few
            # seconds, one after another.
            #
            # Threads rather than asyncio: the Mistral client here is sync, and
            # documentChunking itself is called from a thread by the ingestion
            # service. Capped because every window competes for the same key
            # pool, and firing 20 at once just rate-limits every key at the
            # same moment.
            raw_secs = []
            with ThreadPoolExecutor(max_workers=CHUNK_CONCURRENCY) as pool:
                for sections in pool.map(self._sections_for, prompts):
                    raw_secs.extend(sections)

            raw_secs.sort(key=lambda s: s.start_line)
            secs = []
            for s in raw_secs:
                if not secs or s.start_line > secs[-1].start_line:
                    secs.append(s)
            assert len(secs) >= 2
            assert all(0 <= s.start_line < len(lines) for s in secs)
            assert all(secs[i].start_line < secs[i+1].start_line for i in range(len(secs)-1))
            llm_chunks = []
            for i, s in enumerate(secs):
                end = secs[i+1].start_line if i+1 < len(secs) else len(lines)
                content = "\n".join(lines[s.start_line:end]).strip()    
                if content:
                    llm_chunks.append({"topic": s.topic.rstrip(": ").strip(), "parent": s.parent.rstrip(": ").strip() if s.parent else None, "content": content})
            return llm_chunks
        except Exception as e:
            raise CustomException(e, sys)
