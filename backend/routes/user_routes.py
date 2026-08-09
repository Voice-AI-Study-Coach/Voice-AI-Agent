import sys
import os

from fastapi import APIRouter, Depends
from fastapi.requests import Request
from fastapi.exceptions import HTTPException
from backend.models.user_schemas import Signup, Login
from src.exception import CustomException
from backend.controllers.user_controllers import handleSignupController, handleLoginController, handleLogoutController, handleMeController
from backend.middlewares.auth_middleware import verify_jwt

user_router = APIRouter()

@user_router.post("/signup")
def signup(user: Signup):
    try:
        return handleSignupController(user=user)
    except HTTPException:
        raise
    except Exception as e:
        raise CustomException(e, sys)

@user_router.post("/login")
def login(user: Login):
    try:
        return handleLoginController(user=user)
    except HTTPException:
        raise
    except Exception as e:
        raise CustomException(e, sys)

@user_router.get("/me", dependencies=[Depends(verify_jwt)])
def me(request: Request):
    try:
        return handleMeController(request=request)
    except HTTPException:
        raise
    except Exception as e:
        raise CustomException(e, sys)

@user_router.delete("/logout", dependencies=[Depends(verify_jwt)])
def logout(request: Request):
    try:
        return handleLogoutController(request=request)
    except HTTPException:
        raise
    except Exception as e:
        raise CustomException(e, sys)
