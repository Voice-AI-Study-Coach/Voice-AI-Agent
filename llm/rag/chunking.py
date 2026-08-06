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
from dotenv import load_dotenv

load_dotenv()

class Chunking:
    def __init__(self, doc, toc):
        self.doc = doc
        self.toc = toc
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
            llm = ChatGroq(model='llama-3.3-70b-versatile', temperature=0)
            structured = llm.with_structured_output(schema=Sections)

            WINDOW = 150
            raw_secs = []

            for start in range(0, len(lines), WINDOW):
                window = lines[start:start + WINDOW]
                numbered_w = "\n".join(f"{start+i}: {l}" for i, l in enumerate(window))
                prompt = chunking_prompt(hints=hints, numbered_w=numbered_w)
                raw_secs.extend(structured.invoke(prompt).sections)
                
            raw_secs.sort(key=lambda s: s.start_line)
            secs = []
            for s in raw_secs:
                if not secs or s.start_line > secs[-1].start_line:
                    secs.append(s)
            return secs
        except Exception as e:
            raise CustomException(e, sys)
