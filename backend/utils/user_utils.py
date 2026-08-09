import os
import jwt
import sys
import bcrypt

from src.exception import CustomException

def createToken(payload, key, algorithm):
    try:
        token = jwt.encode(payload, key, algorithm)
        return token
    except Exception as e:
        raise CustomException(e, sys)

def verify_password(plain: str, hashed) -> bool:
   try:
        if isinstance(hashed, str):
            hashed = hashed.encode("utf-8")
        return bcrypt.checkpw(plain.encode("utf-8"), hashed)
   except Exception as e:
       raise CustomException(e, sys)