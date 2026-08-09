import sys
import bcrypt
import os
import datetime

from src.exception import CustomException
from supabase_client.client import client
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException
from backend.utils.user_utils import createToken
from dotenv import load_dotenv
from backend.utils.user_utils import verify_password

load_dotenv()

def handleSignupController(user):
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
    except HTTPException:
        raise
    except Exception as e:
        raise CustomException(e, sys)
    
def handleLoginController(user):
    try:
        response = (
            client.table("users")
            .select("user_id, name, email, password")
            .eq("email", user.email)
            .execute()
        )
        if not response.data:
            raise HTTPException(status_code=404, detail="User not found.Please signup first")
        data = response.data[0]
        isPasswordCorrect = verify_password(user.password, data['password'])
        if not isPasswordCorrect:
            raise HTTPException(status_code=401, detail="Please provide a correct password")
        # The password hash is deliberately NOT in the token: a JWT is only
        # signed, not encrypted, so anyone holding it can read every claim.
        # The expiry matches the cookie's max_age below - a token that
        # outlives its cookie makes /auth/me meaningless as a validity check.
        payload = {
                    "user_id": data['user_id'],
                    "name": data['name'],
                    "email": data['email'],
                    "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30)
                }
        token = createToken(payload=payload, key=os.environ.get("JWT_SECRET_KEY"), algorithm="HS256")
        json_response = JSONResponse(status_code=200, content={"message": "User logged in successfully", "name": data['name']})
        json_response.set_cookie(
            key='access_token',
            value=token,
            httponly=True,
            max_age=30 * 24 * 60 * 60,  # 30 days in seconds
            samesite="lax",
            path="/"
        )
        return json_response
    except HTTPException:
        raise
    except Exception as e:
        raise CustomException(e, sys)

def handleMeController(request):
    """The frontend calls this on page load to learn whether the cookie is
    still valid and who is logged in. verify_jwt has already decoded the token
    and confirmed the user row exists."""
    try:
        user = request.state.user
        return {
            "user_id": user["user_id"],
            "name": user["name"],
            "email": user["email"],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise CustomException(e, sys)

def handleLogoutController(request):
    try:
        response = (
            client.table("users")
            .select("email")
            .eq("email", request.state.user['email'])
            .execute()
        )
        if not response.data:
            raise HTTPException(status_code=404, detail="User not found.Please login first")
        json_response = JSONResponse(status_code=200, content="User logged out successfully")
        json_response.delete_cookie("access_token")
        return json_response
    except HTTPException:
        raise
    except Exception as e:
        raise CustomException(e, sys)