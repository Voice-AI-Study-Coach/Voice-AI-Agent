import os
import pymupdf as fitz
import sys
import base64

from concurrent.futures import ThreadPoolExecutor

from langchain_core.messages import HumanMessage
from src.exception import CustomException
from llm.schemas import PageBlocks, DocumentStructured, TopicClusters
from llm.prompts import transcribe_prompt, group_prompt, cluster_topics_prompt
from llm.rotation_shifting import mistral_pool, is_rate_limit_error
from langchain_mistralai import ChatMistralAI
from src.logger import logging

# Pixtral reads the page images; the grouping pass over the transcribed text
# is plain reasoning, so it uses the same text model as the rest of the pipeline.
VISION_MODEL = "pixtral-12b-2409"
REASONING_MODEL = "open-mistral-7b"

import time

# How many pages are transcribed at once. Concurrency is kept modest (2) to
# prevent bursting account-level RPM quotas on Mistral's API.
OCR_PAGE_CONCURRENCY = 2

# Transcribed blocks per grouping call. Grouping used to be a single call over
# the whole document, which does not fail cleanly: 100 pages of blocks is a
# legal prompt (well under the context limit) that Mistral takes longer to
# answer than the HTTP read timeout allows, so the client retries the same
# huge payload, rate-limits itself, and never finishes.
#
# Too small is its own failure: at 50 a 103-page document became 32 windows,
# each too narrow a slice to tell a continuation from a new topic, so the
# merge collapsed only 197 chunks into 155 - a fragmented document, and 155
# question-generation calls behind it. Bigger windows see more context and
# name topics more consistently, which is what the merge matches on.
GROUP_WINDOW_BLOCKS = 150


class OCRChunking:
    def __init__(self, pdf_path):
        self.pdf_path = pdf_path

    def convert_page_to_image(self, path: str, page_num: int = 0, dpi: int = 140) -> str:
        try:
            """Renders a PDF page to base64 JPEG to avoid context length overflow."""
            doc = fitz.open(path)
            page = doc[page_num]
            pix = page.get_pixmap(dpi=dpi)
            jpeg_bytes = pix.tobytes("jpeg", jpg_quality=80)
            return base64.b64encode(jpeg_bytes).decode("utf-8")
        except Exception as e:
            raise CustomException(e, sys)

    def build_transcribe_msg(self, img_b64: str):
        try:
            return [
                    HumanMessage(content=[
                        {"type": "text", "text": transcribe_prompt()},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                    ])
                ]
        except Exception as e:
            raise CustomException(e, sys)
            
    def _structured_mistral(self, schema, model: str = VISION_MODEL):
        try:
            """Build a ChatMistralAI structured-output client on a key that isn't rate-limited.
            
            The key is fetched per call, never cached on self: a key held from
            __init__ could not rotate away once it got cooled down.
            """
            key = mistral_pool.get_key()
            llm = ChatMistralAI(model=model, temperature=0, api_key=key)
            return key, llm.with_structured_output(schema=schema)
        except Exception as e:
            raise CustomException(e, sys)
        
    def _invoke_with_rotation(self, messages, schema, model: str = VISION_MODEL):
        """Invoke Mistral with key rotation, request pacing, and jittered backoff.

        Rotates across available keys on 429 rate-limit errors. Outer retries (3 passes)
        ensure per-second account RPM bursts cool down safely without failing ingestion.
        """
        last_exc = None
        for attempt in range(3):
            for _ in range(len(mistral_pool._keys)):
                key, structured = self._structured_mistral(schema, model)
                try:
                    result = structured.invoke(messages)
                    mistral_pool.mark_success(key)
                    return result
                except Exception as e:
                    if is_rate_limit_error(e):
                        mistral_pool.mark_rate_limited(key)
                        last_exc = e
                        time.sleep(0.3)  # brief stagger before picking next key
                        continue
                    raise
            time.sleep(2.0)  # if all keys are cooling down, pause briefly before next pass
        raise CustomException(last_exc or "All Mistral keys are rate-limited", sys)

    def transcribe_page(self, page_num: int = 0, dpi: int = 140) -> PageBlocks:
        """Transcribe one page. The image is rasterised and the message built
        once, outside the retry loop, so a rotation retry does not re-render
        the page or change the payload size."""
        try:
            img_b64 = self.convert_page_to_image(self.pdf_path, page_num=page_num, dpi=dpi)
            messages = self.build_transcribe_msg(img_b64)
            return self._invoke_with_rotation(messages, PageBlocks)
        except Exception as e:
            raise CustomException(e, sys)

    def _blocks_for_page(self, page_num: int) -> list[str]:
        """One page's transcribed blocks. Separate method so it can be mapped
        over a thread pool; the key rotation inside is already per-call and
        thread-safe (KeyPool guards its own state with a lock)."""
        time.sleep(0.2)  # pace page dispatch to avoid account RPM spikes
        img_b64 = self.convert_page_to_image(self.pdf_path, page_num=page_num)
        response = self._invoke_with_rotation(
            self.build_transcribe_msg(img_b64), PageBlocks
        )
        logging.info(f"Transcribed page {page_num + 1}")
        return response.blocks if response is not None else []

    def _chunks_for_window(self, window: list[str]):
        """One window's topic chunks. Separate method so it can be mapped over
        a thread pool, the same way _blocks_for_page is."""
        time.sleep(0.3)  # pace window dispatch to avoid account RPM spikes
        transcription = "\n\n---BLOCK---\n\n".join(window)
        messages = [
            HumanMessage(
                content=f"{group_prompt()}\n\nDOCUMENT BLOCKS:\n{transcription}"
            )
        ]
        result = self._invoke_with_rotation(
            messages, DocumentStructured, model=REASONING_MODEL
        )
        return result.chunks if result is not None else []

    def _canonical_topics(self, names: list[str]) -> dict[str, str]:
        """Map every topic name onto a canonical one, so names that mean the
        same thing merge into a single chunk.

        Each grouping window names its topics independently, so one section
        comes back as "Merge Sort", "Merge Sort Algorithm", "Merge Sort
        (contd)" and never merges on an exact string match. This pass sends
        only the NAMES - never the content - so it stays one small, fast call
        however long the document is.

        Failing here is not worth failing ingestion over: on any error the
        names are returned unchanged, which just leaves the exact-match
        merging that would have happened anyway.
        """
        unique = list(dict.fromkeys(names))
        if len(unique) < 2:
            return {}

        try:
            messages = [HumanMessage(content=cluster_topics_prompt(unique))]
            result = self._invoke_with_rotation(
                messages, TopicClusters, model=REASONING_MODEL
            )

            known = set(unique)
            mapping = {}
            for cluster in result.clusters:
                # The model is told to copy variants verbatim, but a
                # hallucinated or reworded one would silently rename a topic
                # and break the join with the questions table, so only names
                # that actually came from this document are mapped.
                for variant in cluster.variants:
                    if variant in known:
                        mapping[variant] = cluster.canonical.strip()

            logging.info(
                f"Topic clustering: {len(unique)} names -> "
                f"{len(set(mapping.values()) | (known - mapping.keys()))} canonical"
            )
            return mapping
        except Exception as e:
            logging.warning(f"Topic clustering failed, keeping raw names: {e}")
            return {}

    def generateOCRChunks(self):
        """Transcribe every page, then group the blocks into topic chunks.

        Two stages, mirroring the notebook probe: a vision pass per page
        (Pixtral reads the handwriting into flat blocks), then one reasoning
        pass over the concatenated blocks that merges continuations spanning
        page breaks into coherent chunks. Both go through the key pool.
        """
        try:
            doc = fitz.open(self.pdf_path)
            try:
                page_count = doc.page_count
            finally:
                doc.close()
            logging.info(f"OCR transcription starting across {page_count} pages")

            # One vision call per page, run CONCURRENTLY. Serially this is the
            # slowest part of OCR ingestion by far: every page is a full
            # round trip to Pixtral, so a 20-page document spends minutes
            # waiting one page at a time.
            #
            # pool.map preserves input order, which matters here in a way it
            # does not for text chunking: the blocks carry no line numbers, so
            # reading order is the only thing letting the grouping pass merge
            # an algorithm or derivation that runs across a page break.
            #
            # Capped for the same reason as CHUNK_CONCURRENCY: every page
            # competes for the same Mistral key pool, and firing all of them
            # at once just rate-limits every key at the same moment, after
            # which the rotation loop serialises them anyway.
            all_blocks = []
            with ThreadPoolExecutor(max_workers=OCR_PAGE_CONCURRENCY) as pool:
                for blocks in pool.map(self._blocks_for_page, range(page_count)):
                    all_blocks.extend(blocks)

            if not all_blocks:
                return []

            # Grouped in windows, CONCURRENTLY, for the same reason
            # documentChunking splits printed PDFs into 150-line windows: one
            # call carrying the whole document is not just slow, it never
            # completes (see GROUP_WINDOW_BLOCKS).
            #
            # The cost is that a topic running across a window boundary comes
            # back as two chunks, one per window - merged by topic below.
            windows = [
                all_blocks[i:i + GROUP_WINDOW_BLOCKS]
                for i in range(0, len(all_blocks), GROUP_WINDOW_BLOCKS)
            ]
            logging.info(
                f"Grouping {len(all_blocks)} blocks in {len(windows)} windows"
            )

            raw_chunks = []
            with ThreadPoolExecutor(max_workers=OCR_PAGE_CONCURRENCY) as pool:
                for chunks in pool.map(self._chunks_for_window, windows):
                    raw_chunks.extend(chunks)

            if not raw_chunks:
                return []

            # Flattened to the same list-of-dicts shape documentChunking
            # returns, so embedding, question generation and insert_chunks all
            # take this path unchanged. Handing the Pydantic model downstream
            # instead means every stage needs an OCR-specific variant.
            #
            # topic is Optional on TopicChunk, but chunks.topic is the string
            # the questions and turns tables join on - a null there does not
            # error, it just silently loses grading its source material - so a
            # chunk without one falls back to its parent.
            # Merged on the topic string, which is what stitches a topic back
            # together when it ran across a window boundary and each window
            # reported its own half. Insertion order is kept, so the halves
            # rejoin in reading order and the document still reads front to
            # back. This only works as well as the model's consistency in
            # naming a topic the same way twice.
            names = [(c.topic or c.parent).rstrip(": ").strip() for c in raw_chunks]
            canonical = self._canonical_topics(names)

            merged: dict[str, dict] = {}
            for c, name in zip(raw_chunks, names):
                topic = canonical.get(name, name)
                parent = c.parent.rstrip(": ").strip() if c.parent else None
                if topic in merged:
                    merged[topic]["content"] += "\n\n" + c.content
                else:
                    merged[topic] = {
                        "topic": topic,
                        "parent": parent,
                        "content": c.content,
                    }

            logging.info(
                f"Grouped into {len(raw_chunks)} raw chunks -> {len(merged)} topics"
            )
            return list(merged.values())
        except CustomException:
            raise
        except Exception as e:
            raise CustomException(e, sys)

if __name__=="__main__":
    ocr = OCRChunking(pdf_path=r'C:\Voice Agent\testing\docs\DM - 2.pdf')
    result = ocr.generateOCRChunks()
    i = 1
    for c in result:
        print(f"CHUNK: {i}")
        print(f"PARENT: {c['parent']}")
        print(f"TOPIC: {c['topic']}")
        print(f"CONTENT: {c['content']}")
        print("\n")
        i+=1