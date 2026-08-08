import sys
import asyncio
import time
from collections import defaultdict

from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_cerebras import ChatCerebras
from langchain_classic.output_parsers import PydanticOutputParser

from src.exception import CustomException
from llm.schemas import GeneratedQuestions
from llm.prompts import build_q_prompt
from llm.rotation_shifting import groq_pool, is_rate_limit_error, is_transient_tool_error

load_dotenv()


class QuestionGenerator:
    def __init__(self, chunks, concurrency: int = 3):
        self.chunks = chunks
        self.sem = asyncio.Semaphore(concurrency)

    def _structured_groq(self):
        """Build a Groq structured-output client using a key that isn't rate-limited.

        Uses json_mode instead of native tool-calling: Groq's function-call
        framing is prone to "tool_use_failed" on short/terse fields (common in
        low-difficulty questions), whereas json_mode just asks for raw JSON
        and is far more reliable for this schema.
        """
        key = groq_pool.get_key()
        model = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.1, api_key=key)
        return key, model.with_structured_output(schema=GeneratedQuestions, method="json_mode")

    async def gen_one(self, topic, parent, chunk_list):
        content = "\n\n".join(c["content"] for c in chunk_list)
        prompt = build_q_prompt(
            topic,
            content
        )

        async with self.sem:
            max_key_rotations = len(groq_pool._keys)
            for attempt in range(4):
                result, hard_error = None, None

                for _ in range(max_key_rotations):
                    key, structured = self._structured_groq()
                    try:
                        result = await structured.ainvoke(prompt)
                        groq_pool.mark_success(key)
                        break
                    except Exception as e:
                        if is_rate_limit_error(e):
                            groq_pool.mark_rate_limited(key)
                            continue
                        if is_transient_tool_error(e):
                            # not a rate limit, but worth retrying (via the
                            # outer attempt/backoff loop) instead of a hard fail
                            hard_error = None
                            break
                        hard_error = e
                        break

                if result is not None:
                    return [
                        {**q.model_dump(), "topic": topic, "parent": parent}
                        for q in result.questions
                    ]

                if attempt == 3 or hard_error is not None:
                    reason = hard_error if hard_error is not None else "all Groq keys rate-limited"
                    print(f"  {topic} failed: {reason}")
                    return []
                await asyncio.sleep(2 ** attempt)

    async def generateQuestions(self):
        try:
            gen_chunks = [c for c in self.chunks if len(c["content"]) // 4 >= 100]

            by_topic = defaultdict(list)
            for c in gen_chunks:
                by_topic[c["topic"].rstrip(": ").strip()].append(c)

            print(f"{len(self.chunks)} chunks -> {len(gen_chunks)} usable -> {len(by_topic)} topics")

            t0 = time.perf_counter()
            batches = await asyncio.gather(*[
                self.gen_one(topic, cs[0].get("parent"), cs)
                for topic, cs in by_topic.items()
            ])
            all_questions = [q for b in batches for q in b]

            print(f"{time.perf_counter() - t0:.1f}s | {len(by_topic)} calls | {len(all_questions)} questions")
            return all_questions
        except Exception as e:
            raise CustomException(e, sys)