import sys
import asyncio
import logging

from datetime import datetime, timezone
from src.exception import CustomException
from llm.rag.ingestion import DocumentIngestion
from llm.rag.chunking import Chunking
from llm.rag.embedding import Embedding
from llm.rag.generation import QuestionGenerator
from backend.db import execute, fetch_one
from backend.utils.rag_utils import insert_chunks, insert_questions

log = logging.getLogger(__name__)


async def run_ingestion(document_id: int) -> None:
    """
    Full ingestion pipeline. Runs as a FastAPI background task, so it must
    never raise - any exception is caught and recorded on the document row
    instead, otherwise the document is left stuck in 'processing' forever
    with no way for the user to know what happened.
    """
    log.info("run_ingestion: starting document_id=%s", document_id)
    try:
        set_document_status(document_id=document_id, status="processing")

        # --- 1. read the PDF -------------------------------------------
        path = get_document_path(document_id)
        log.debug("run_ingestion: document_id=%s storage_path=%s", document_id, path)
        if not path:
            raise ValueError("Document row is missing its storage_path")

        ingestion = DocumentIngestion(path=path)
        doc, toc = ingestion.loadDocument()
        log.info("run_ingestion: document_id=%s loaded pdf pages=%d toc_entries=%d",
                  document_id, doc.page_count, len(toc))

        full = ""
        page_starts = []
        for p in range(doc.page_count):
            page_starts.append(len(full))
            full += doc[p].get_text()

        # --- 2. guard: scanned / image-only PDFs ------------------------
        if len(full.strip()) < 200:
            raise ValueError(
                "No extractable text found. This PDF appears to be scanned "
                "or image-based; please upload a text-based PDF."
            )

        # --- 3. chunk -----------------------------------------------------
        chunking = Chunking(doc=doc, toc=toc)
        chunks = chunking.documentChunking()
        if not chunks:
            raise ValueError("Chunking produced no sections from this document")

        log.info("run_ingestion: document_id=%s chunked into %d chunks", document_id, len(chunks))

        # --- 4. embed + generate, concurrently ---------------------------
        # Independent of each other: both read chunk content, neither reads
        # the other's output. Embedding takes seconds, generation takes
        # minutes, so running them together makes the embedding cost
        # effectively free. generateEmbedding is sync, so it runs in a
        # thread; generateQuestions is already async.
        embedder = Embedding(chunks)
        generator = QuestionGenerator(chunks)

        log.info("run_ingestion: document_id=%s starting embed+generate", document_id)
        embedded_chunks, questions = await asyncio.gather(
            asyncio.to_thread(embedder.generateEmbedding),
            generator.generateQuestions(),
        )
        log.info("run_ingestion: document_id=%s embed+generate done, embedded=%d questions=%d",
                  document_id, len(embedded_chunks), len(questions))

        # --- 5. persist ----------------------------------------------------
        # Chunks first: they must exist before anything references them,
        # and retrieval/grading is useless without them.
        insert_chunks(document_id, embedded_chunks)
        log.info("run_ingestion: document_id=%s chunks persisted", document_id)

        if not questions:
            raise ValueError("Question generation produced no questions")
        insert_questions(document_id, questions)
        log.info("run_ingestion: document_id=%s questions persisted", document_id)

        # --- 6. done ---------------------------------------------------
        set_document_status(document_id=document_id, status="ready", processed=True)
        log.info("run_ingestion: document_id=%s READY", document_id)

    except Exception as e:
        log.exception("run_ingestion: FAILED document_id=%s", document_id)
        set_document_status(document_id=document_id, status="failed", error=str(e)[:500])


def get_document_path(document_id):
    try:
        row = fetch_one(
            "select storage_path from documents where document_id = %s",
            (document_id,),
        )
        return row["storage_path"] if row else None
    except Exception as e:
        raise CustomException(e, sys)


def set_document_status(document_id: int, status: str, error: str | None = None, processed: bool = False):
    try:
        execute(
            """
            update documents set
                status = %s,
                error = coalesce(%s, error),
                processed_at = case when %s then %s else processed_at end
            where document_id = %s
            """,
            (status, error, processed, datetime.now(timezone.utc), document_id),
        )
    except Exception as e:
        raise CustomException(e, sys)
