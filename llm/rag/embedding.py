import os
import sys

from src.exception import CustomException
from src.logger import logging
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from llm.rotation_shifting import gemini_pool, is_rate_limit_error
from dotenv import load_dotenv
from supabase_client.client import client

load_dotenv()


class Embedding:
    def __init__(self, chunks):
        self.chunks = chunks

    def _embedder(self):
        """Build a Gemini embeddings client using a key that isn't rate-limited."""
        key = gemini_pool.get_key()
        # output_dimensionality=768 matches the chunks.embedding vector(768)
        # column in Supabase; the model's default output is 3072-dim, which
        # pgvector rejects outright on insert.
        model = GoogleGenerativeAIEmbeddings(
            model="gemini-embedding-2",
            google_api_key=key,
            output_dimensionality=768,
        )
        return key, model

    def generateEmbedding(self):
        """Embed all chunks in one batch call, rotating keys on rate-limit errors."""
        try:
            texts = [c["content"] for c in self.chunks]

            last_exc = None
            for _ in range(len(gemini_pool._keys)):
                key, model = self._embedder()
                try:
                    vectors = model.embed_documents(texts)
                    gemini_pool.mark_success(key)
                    return [
                        {**chunk, "embedding": vector}
                        for chunk, vector in zip(self.chunks, vectors)
                    ]
                except Exception as e:
                    if is_rate_limit_error(e):
                        gemini_pool.mark_rate_limited(key)
                        last_exc = e
                        continue
                    raise

            raise CustomException(last_exc or "All Gemini keys are rate-limited", sys)
        except Exception as e:
            raise CustomException(e, sys)