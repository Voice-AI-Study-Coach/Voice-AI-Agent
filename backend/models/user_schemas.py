from pydantic import BaseModel, Field, EmailStr
from typing import List, Annotated

class Signup(BaseModel):
    name: str = Field(description="The name of the user")
    email: EmailStr = Field(description="The email of the user")
    password: str = Field(description="The password of the user")

class Login(BaseModel):
    email: EmailStr = Field(description="The email of the user")
    password: str = Field(description="The password of the user")