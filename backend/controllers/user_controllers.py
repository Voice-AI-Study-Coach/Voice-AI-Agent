import sys
import bcrypt
import os

from src.exception import CustomException
from supabase_client.client import client
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException
from dotenv import load_dotenv

load_dotenv()

def getSignupController(user):
    try:
        response = (
            client.table("users")
            .select("email")
            .eq("email", user.email)
            .execute()
        )
        if response.data:
            raise HTTPException(status_code=409, detail="The user already exists")
        hashed_password = bcrypt.hashpw(password=user.password.encode(), salt=bcrypt.gensalt(rounds=15))
        decoded_password = hashed_password.decode()
        response = (
            client.table("users")
            .insert({"name": user.name, "email": user.email, "password": decoded_password})
            .execute()
        )
        if not response.data:
            raise HTTPException(status_code=500, detail="Something went wrong while inserting the data")
        return JSONResponse(content="User signed up successfully", status_code=201)
    except Exception as e:
        raise CustomException(e, sys)
    
def getLoginController(user):
    try:
        response = (
            client.table("users")
            .select("email", user.email)
            .execute()
        )
        if not response.data:
            raise HTTPException(status_code=404, detail="User not found.Please signup first")
    except Exception as e:
        raise CustomException(e, sys)