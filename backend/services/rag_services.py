import sys
import asyncio
import logging

import pymupdf as fitz

from datetime import datetime, timezone
from src.exception import CustomException
from llm.rag.ingestion import DocumentIngestion
from llm.rag.chunking import Chunking
from llm.rag.ocr_chunking import OCRChunking
from llm.rag.embedding import Embedding
from llm.rag.generation import QuestionGenerator
from backend.config import TEXT_LAYER_MIN_CHARS
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
        # newChat routes these to run_ocr_ingestion instead, so reaching this
        # means the document was queued here directly. Kept as a safety net:
        # chunking a document with no text produces nothing usable.
        if len(full.strip()) < TEXT_LAYER_MIN_CHARS:
            raise ValueError(
                "No extractable text found. This PDF appears to be scanned "
                "or image-based; it should go through the OCR pipeline."
            )

        # --- 3. chunk -----------------------------------------------------
        chunking = Chunking(doc=doc, toc=toc)
        chunks = chunking.documentChunking()
        if not chunks:
            raise ValueError("Chunking produced no sections from this document")

        log.info("run_ingestion: document_id=%s chunked into %d chunks", document_id, len(chunks))

        # --- 4. embed & persist chunks immediately -----------------------
        embedder = Embedding(chunks)
        embedded_chunks = await asyncio.to_thread(embedder.generateEmbedding)
        insert_chunks(document_id, embedded_chunks)
        log.info("run_ingestion: document_id=%s chunks persisted", document_id)

        # --- 5. mark status GENERATING for frontend streaming -------------
        set_document_status(document_id=document_id, status="generating", processed=False)
        log.info("run_ingestion: document_id=%s GENERATING (live topic streaming active)", document_id)

        # --- 6. generate & stream questions topic-by-topic ----------------
        generator = QuestionGenerator(chunks, document_id=document_id)
        questions = await generator.generateQuestions()
        
        # --- 7. mark status READY once all question generation is complete ---
        set_document_status(document_id=document_id, status="ready", processed=True)
        log.info("run_ingestion: document_id=%s READY (all %d questions persisted)",
                 document_id, len(questions))

    except Exception as e:
        log.exception("run_ingestion: FAILED document_id=%s", document_id)
        set_document_status(document_id=document_id, status="failed", error=str(e)[:500])

async def run_ocr_ingestion(document_id: int) -> None:
    """
    Full ingestion pipeline. Runs as a FastAPI background task, so it must
    never raise - any exception is caught and recorded on the document row
    instead, otherwise the document is left stuck in 'processing' forever
    with no way for the user to know what happened.
    """
    log.info("run_ocr_ingestion: starting document_id=%s", document_id)
    try:
        set_document_status(document_id=document_id, status="processing")

        # --- 1. read the PDF -------------------------------------------
        path = get_document_path(document_id)
        log.debug("run_ocr_ingestion: document_id=%s storage_path=%s", document_id, path)
        if not path:
            raise ValueError("Document row is missing its storage_path")

        # --- 3. chunk -----------------------------------------------------
        chunking = OCRChunking(pdf_path=path)
        # to_thread, not a direct call: generateOCRChunks is fully synchronous
        # (PyMuPDF rasterising, then a blocking vision call per page), and a
        # background task runs on the event loop like any other coroutine.
        # Called directly it parks the loop for the whole OCR run and every
        # other request in the process waits behind it.
        chunks = await asyncio.to_thread(chunking.generateOCRChunks)
        if not chunks:
            raise ValueError("Chunking produced no sections from this document")

        log.info("run_ocr_ingestion: document_id=%s chunked into %d chunks",
                 document_id, len(chunks))

        # --- 4. embed & persist chunks immediately -----------------------
        embedder = Embedding(chunks)
        embedded_chunks = await asyncio.to_thread(embedder.generateEmbedding)
        insert_chunks(document_id, embedded_chunks)
        log.info("run_ocr_ingestion: document_id=%s chunks persisted", document_id)

        # --- 5. mark status GENERATING for frontend streaming -------------
        set_document_status(document_id=document_id, status="generating", processed=False)
        log.info("run_ocr_ingestion: document_id=%s GENERATING (live topic streaming active)", document_id)

        # --- 6. generate & stream questions topic-by-topic ----------------
        generator = QuestionGenerator(chunks, document_id=document_id)
        questions = await generator.generateQuestions()

        # --- 7. mark status READY once all question generation is complete ---
        set_document_status(document_id=document_id, status="ready", processed=True)
        log.info("run_ocr_ingestion: document_id=%s READY (all %d questions persisted)",
                 document_id, len(questions))

    except Exception as e:
        log.exception("run_ingestion: FAILED document_id=%s", document_id)
        set_document_status(document_id=document_id, status="failed", error=str(e)[:500])


def has_text_layer(path: str) -> bool:
    """True if the PDF carries an extractable text layer.

    Printed PDFs return their text from get_text(); handwritten and scanned
    ones have no text layer and come back effectively empty, which is what
    routes them to the OCR pipeline instead. The two cases are not worth
    telling apart - both need the same vision pass.

    The threshold matches the guard that used to live in run_ingestion: a few
    stray characters (a watermark, a page number picked up from a scan) are
    not a usable text layer.
    """
    try:
        doc = fitz.open(path)
        try:
            text = "".join(doc[p].get_text() for p in range(doc.page_count))
        finally:
            doc.close()
        return len(text.strip()) >= TEXT_LAYER_MIN_CHARS
    except Exception as e:
        raise CustomException(e, sys)


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
