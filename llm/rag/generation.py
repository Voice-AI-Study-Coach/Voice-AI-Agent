import sys
import asyncio
import time

from dotenv import  load_dotenv
from langchain_ollama import ChatOllama
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from src.exception import CustomException
from llm.schemas import GeneratedQuestions
from llm.prompts import build_q_prompt
from langchain_classic.output_parsers import PydanticOutputParser

load_dotenv()

class QuestionGenerator:
    def __init__(self, chunks):
        self.chunks = chunks

    async def gen_one(self, idx, c):
            try:
                model = ChatOllama(model='phi4-mini:latest', temperature=0.2)
                parser = PydanticOutputParser(pydantic_object=GeneratedQuestions)
                sem = asyncio.Semaphore(5)
                n = max(2, min(6, len(c["content"]) // 400))
                async with sem:
                    for attempt in range(4):
                        try:
                            r = await model.invoke(build_q_prompt(c["topic"], c["content"], n, parser.get_format_instructions()))
                            return [{**q.model_dump(),
                                        "topic": c["topic"].rstrip(": ").strip(),
                                        "chunk_idx": idx} for q in r.questions]
                        except Exception as e:
                            if attempt == 3:
                                print(f"  [{idx}] {c['topic']} failed: {e}")
                                return []
                            await asyncio.sleep(2 ** attempt)
            except Exception as e:
                raise CustomException(e, sys)
    
    async def generateQuestions(self):
        try:
            gen_chunks = [c for c in self.chunks if len(c['content']) // 4 >= 100]
            t0 = time.perf_counter()
            batches = await asyncio.gather(*[self.gen_one(i, c) for i, c in enumerate(gen_chunks)])
            all_questions = [q for b in batches for q in b]
            return all_questions
        except Exception as e:  
            raise CustomException(e, sys)    