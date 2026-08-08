import os
import jwt
import sys

from src.exception import CustomException

def createToken(payload, key, algorithm):
    try:
        pass
    except Exception as e:
        raise CustomException(e, sys)