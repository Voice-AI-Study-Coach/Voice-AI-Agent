import sys
import os

from fastapi import APIRouter
from fastapi.requests import Request
from backend.models.user_schemas import Signup, Login
from src.exception import CustomException
from backend.controllers.user_controllers import handleSignupController, handleLoginController, handleLogoutController

user_router = APIRouter()

@user_router.post("/signup")
def signup(user: Signup):
    try:
        return handleSignupController(user=user)
    except Exception as e:
        raise CustomException(e, sys)

@user_router.post("/login")
def login(user: Login):
    try:
        return handleLoginController(user=user)
    except Exception as e:
        raise CustomException(e, sys)

@user_router.delete("/logout")
def logout(request: Request):
    try:
        return handleLogoutController(request=request)
    except Exception as e:
        raise CustomException(e, sys)
