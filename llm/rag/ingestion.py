import os
import pymupdf as fitz
import sys

from src.logger import logging
from src.exception import CustomException
from llm.rag.chunking import Chunking

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

if __name__=="__main__":
    ingestion = DocumentIngestion(path=r'C:\Voice Agent\testing\docs\Unit-1.pdf')
    documents = ingestion.loadDocument()
    chunking = Chunking(doc=documents[0], toc=documents[1])
    secs = chunking.documentChunking()
    print(len(secs), "sections")
    for s in secs:
        print(s.start_line, "|", s.topic)