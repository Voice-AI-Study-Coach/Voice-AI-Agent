import os
import sys
import jwt

from src.exception import CustomException
from dotenv import load_dotenv
from fastapi import HTTPException
from fastapi.requests import Request
from supabase_client.client import client

def verify_jwt(request: Request):
    try:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.removeprefix("Bearer ").strip()
        else:
            token = request.cookies.get("access_token")

        if not token:
            raise HTTPException(status_code=401, detail="Missing access token")

        try:
            decodedToken = jwt.decode(token, os.environ.get("JWT_SECRET_KEY"), algorithms=["HS256"])
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid or expired access token")

        user = (
            client.table("users")
            .select("user_id, name, email")
            .eq("user_id", decodedToken['user_id'])
            .execute()
        )
        if not user.data:
            raise HTTPException(status_code=401, detail="Invalid access token")
        request.state.user = user.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise CustomException(e, sys)