import os
import sys

from src.exception import CustomException
from src.logger import logging
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_mistralai import MistralAIEmbeddings
from llm.rotation_shifting import gemini_pool, is_rate_limit_error, mistral_pool
from dotenv import load_dotenv

load_dotenv()


class Embedding:
    def __init__(self, chunks):
        self.chunks = chunks

    def _embedder(self):
        """Build a Gemini embeddings client using a key that isn't rate-limited."""
        key = mistral_pool.get_key()
        # output_dimensionality=768 matches the chunks.embedding vector(768)
        # column; the model's default output is 3072-dim, which pgvector
        # rejects outright on insert.
        model = MistralAIEmbeddings(
            model="mistral-embed-2312",
            api_key=key,
        )
        return key, model

    def generateEmbedding(self):
        """Embed all chunks in one batch call, rotating keys on rate-limit errors."""
        try:
            texts = [c["content"] for c in self.chunks]

            last_exc = None
            for _ in range(len(mistral_pool._keys)):
                key, model = self._embedder()
                try:
                    vectors = model.embed_documents(texts)
                    mistral_pool.mark_success(key)
                    return [
                        {**chunk, "embedding": vector}
                        for chunk, vector in zip(self.chunks, vectors)
                    ]
                except Exception as e:
                    if is_rate_limit_error(e):
                        mistral_pool.mark_rate_limited(key)
                        last_exc = e
                        continue
                    raise

            raise CustomException(last_exc or "All Gemini keys are rate-limited", sys)
        except Exception as e:
            raise CustomException(e, sys)