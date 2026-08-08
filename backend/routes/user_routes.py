import sys

from fastapi import APIRouter
from backend.models.user_schemas import Signup, Login
from src.exception import CustomException
from backend.controllers.user_controllers import getSignupController, getLoginController

user_router = APIRouter()

@user_router.post("/signup")
def signup(user: Signup):
    try:
        return getSignupController(user=user)
    except Exception as e:
        raise CustomException(e, sys)

@user_router.post("/login")
def login(user: Login):
    try:
        pass
    except Exception as e:
        raise CustomException(e, sys)
