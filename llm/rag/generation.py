import sys
import asyncio
import time
from collections import defaultdict

from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from langchain_groq import ChatGroq
from langchain_mistralai import ChatMistralAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_classic.output_parsers import PydanticOutputParser

from src.exception import CustomException
from llm.schemas import GeneratedQuestions
from llm.prompts import build_q_prompt
from llm.rotation_shifting import mistral_pool, is_rate_limit_error, is_transient_tool_error

load_dotenv()


class QuestionGenerator:
    # Raised from 3: question generation is the longest stage of ingestion (one
    # call per topic, and an OCR'd document has far more topics than a printed
    # one), and by the time it runs the chunking calls that also draw on the
    # Mistral pool have finished. Still well under the number of keys, for the
    # reason CHUNK_CONCURRENCY documents - firing everything at once just
    # rate-limits every key and the rotation loop serialises them anyway.
    def __init__(self, chunks, concurrency: int = 2, document_id: int | None = None):
        self.chunks = chunks
        self.document_id = document_id
        self.sem = asyncio.Semaphore(concurrency)

    def _structured_mistral(self):
        """Build a Mistral structured-output client using a key that isn't rate-limited.

        Uses json_mode instead of native tool-calling: function-call framing is
        prone to "tool_use_failed" on short/terse fields (common in
        low-difficulty questions), whereas json_mode just asks for raw JSON
        and is far more reliable for this schema.
        """
        key = mistral_pool.get_key()
        model = ChatMistralAI(model="open-mistral-7b", temperature=0.1, api_key=key)
        return key, model.with_structured_output(schema=GeneratedQuestions, method="json_mode")

    async def gen_one(self, topic, parent, chunk_list):
        content = "\n\n".join(c["content"] for c in chunk_list)
        prompt = build_q_prompt(
            topic,
            content
        )

        async with self.sem:
            max_key_rotations = len(mistral_pool._keys)
            for attempt in range(4):
                result, hard_error = None, None

                for _ in range(max_key_rotations):
                    key, structured = self._structured_mistral()
                    try:
                        result = await structured.ainvoke(prompt)
                        mistral_pool.mark_success(key)
                        break
                    except Exception as e:
                        if is_rate_limit_error(e):
                            mistral_pool.mark_rate_limited(key)
                            await asyncio.sleep(0.3)
                            continue
                        if is_transient_tool_error(e):
                            # not a rate limit, but worth retrying (via the
                            # outer attempt/backoff loop) instead of a hard fail
                            hard_error = None
                            break
                        hard_error = e
                        break

                if result is not None:
                    topic_qs = [
                        {**q.model_dump(), "topic": topic, "parent": parent}
                        for q in result.questions
                    ]
                    if self.document_id and topic_qs:
                        try:
                            from backend.utils.rag_utils import insert_questions
                            await asyncio.to_thread(insert_questions, self.document_id, topic_qs)
                            print(f"  Persisted {len(topic_qs)} questions for topic '{topic}' (doc_id={self.document_id})")
                        except Exception as exc:
                            print(f"  Failed to persist questions for topic '{topic}': {exc}")
                    return topic_qs

                if attempt == 3 or hard_error is not None:
                    reason = hard_error if hard_error is not None else "all Mistral keys rate-limited"
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
