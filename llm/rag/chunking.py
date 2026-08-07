import os
import sys
import re

from langchain_ollama import ChatOllama
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from src.exception import CustomException
from src.logger import logging
from llm.schemas import Sections
from llm.prompts import chunking_prompt
from llm.rotation_shifting import groq_pool, is_rate_limit_error
from dotenv import load_dotenv
from langchain_classic.output_parsers import PydanticOutputParser

load_dotenv()

class Chunking:
    def __init__(self, doc, toc):
        self.doc = doc
        self.toc = toc

    def _structured_groq(self):
        """Build a ChatGroq structured-output client using a key that isn't rate-limited."""
        key = groq_pool.get_key()
        llm = ChatGroq(model='llama-3.3-70b-versatile', temperature=0, api_key=key)
        return key, llm.with_structured_output(schema=Sections)

    def _invoke_with_rotation(self, prompt):
        """Invoke Groq, rotating to the next available key on rate-limit errors."""
        last_exc = None
        for _ in range(len(groq_pool._keys)):
            key, structured = self._structured_groq()
            try:
                result = structured.invoke(prompt)
                groq_pool.mark_success(key)
                return result
            except Exception as e:
                if is_rate_limit_error(e):
                    groq_pool.mark_rate_limited(key)
                    last_exc = e
                    continue
                raise
        raise CustomException(last_exc or "All Groq keys are rate-limited", sys)

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
            numbered = "\n".join(f"{i}: {l}" for i, l in enumerate(lines))
            WINDOW = 150
            raw_secs = []

            for start in range(0, len(lines), WINDOW):
                window = lines[start:start + WINDOW]
                numbered_w = "\n".join(f"{start+i}: {l}" for i, l in enumerate(window))
                prompt = chunking_prompt(
                    hints=hints,
                    numbered_w=numbered_w
                )
                raw_secs.extend(self._invoke_with_rotation(prompt).sections)
                            
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
                    llm_chunks.append({"topic": s.topic, "parent": s.parent, "content": content})
            return llm_chunks
        except Exception as e:
            raise CustomException(e, sys)
