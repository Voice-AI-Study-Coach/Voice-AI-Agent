import os
import jwt
import sys

from src.exception import CustomException

def createToken(payload, key, algorithm):
    try:
        token = jwt.encode(payload, key, algorithm)
        return token
    except Exception as e:
        raise CustomException(e, sys)