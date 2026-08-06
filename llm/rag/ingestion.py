import os
import pymupdf as fitz
import sys
import asyncio

from src.logger import logging
from src.exception import CustomException
from llm.rag.chunking import Chunking
from llm.rag.generation import QuestionGenerator    

class DocumentIngestion:
    def __init__(self, path):
        self.path = path

    def loadDocument(self):
        try:
            doc = fitz.open(self.path)
            toc = doc.get_toc()
            return (doc, toc)
        except Exception as e:
            raise CustomException(e, sys)

async def main():
    ingestion = DocumentIngestion(path=r'C:\Voice Agent\testing\docs\Unit-1.pdf')
    documents = ingestion.loadDocument()
    chunking = Chunking(doc=documents[0], toc=documents[1])
    chunks = chunking.documentChunking()
    embedding = QuestionGenerator(chunks=chunks)
    questions = await embedding.generateQuestions()
    print(questions)

if __name__ == "__main__":
    asyncio.run(main())