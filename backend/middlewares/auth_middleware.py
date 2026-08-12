import os
import sys
import jwt

from src.exception import CustomException
from dotenv import load_dotenv
from fastapi import HTTPException
from fastapi.requests import Request
from fastapi.websockets import WebSocket
from backend.db import fetch_one


def _resolve_user(token: str | None) -> dict:
    """Shared core of verify_jwt: decode the token and confirm the user
    still exists. Raises HTTPException(401) on any failure - both the HTTP
    and WebSocket callers below translate that the same way, just through
    different transports (a response vs. a close code)."""
    if not token:
        raise HTTPException(status_code=401, detail="Missing access token")
    try:
        decoded = jwt.decode(token, os.environ.get("JWT_SECRET_KEY"), algorithms=["HS256"])
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired access token")
    user = fetch_one(
        "select user_id, name, email from users where user_id = %s",
        (decoded["user_id"],),
    )
    if not user:
        raise HTTPException(status_code=401, detail="Invalid access token")
    return user


def verify_jwt(request: Request):
    try:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.removeprefix("Bearer ").strip()
        else:
            token = request.cookies.get("access_token")
        request.state.user = _resolve_user(token)
    except HTTPException:
        raise
    except Exception as e:
        raise CustomException(e, sys)


async def verify_jwt_ws(websocket: WebSocket) -> dict:
    """WebSocket equivalent of verify_jwt.

    Not usable as a FastAPI `Depends` on a WebSocket route the way verify_jwt
    is on HTTP ones - a WebSocket connection is not a Request, and by the
    time a route body runs the handshake has already been accepted. Callers
    must call this explicitly, before `websocket.accept()`, and close the
    connection themselves if it raises.

    The access_token cookie rides along on the WebSocket handshake the same
    way it does on a normal HTTP request, so no separate auth message from
    the client is needed for the common case.
    """
    try:
        auth_header = websocket.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.removeprefix("Bearer ").strip()
        else:
            token = websocket.cookies.get("access_token")
        return _resolve_user(token)
    except HTTPException:
        raise
    except Exception as e:
        raise CustomException(e, sys)
