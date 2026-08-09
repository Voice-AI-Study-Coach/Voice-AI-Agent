import sys

from fastapi import APIRouter, Depends
from fastapi.requests import Request
from fastapi.exceptions import HTTPException

from src.exception import CustomException
from backend.controllers.session_controllers import (
    handleGetSession,
    handleSession,
    handleSessionSummary,
    handleSubmitAnswer,
)
from backend.middlewares.auth_middleware import verify_jwt
from backend.models.session_schemas import (
    AnswerRequest,
    AnswerResponse,
    SessionReplayResponse,
    StartSession,
    StartSessionResponse,
    SummaryResponse,
)

# Auth at the router level: session ids are sequential integers, so an
# unauthenticated route here would let anyone walk other users' sessions.
session_router = APIRouter(dependencies=[Depends(verify_jwt)])


@session_router.post("/sessions", status_code=201, response_model=StartSessionResponse)
def createSession(request: Request, session: StartSession):
    try:
        return handleSession(request=request, payload=session)
    except HTTPException:
        raise
    except Exception as e:
        raise CustomException(e, sys)


@session_router.post("/sessions/{session_id}/answer", response_model=AnswerResponse)
async def submitAnswer(request: Request, session_id: int, answer: AnswerRequest):
    try:
        return await handleSubmitAnswer(
            request=request, session_id=session_id, payload=answer
        )
    except HTTPException:
        raise
    except Exception as e:
        raise CustomException(e, sys)


@session_router.get("/sessions/{session_id}", response_model=SessionReplayResponse)
def getSession(request: Request, session_id: int):
    try:
        return handleGetSession(request=request, session_id=session_id)
    except HTTPException:
        raise
    except Exception as e:
        raise CustomException(e, sys)


@session_router.get("/sessions/{session_id}/summary", response_model=SummaryResponse)
async def getSessionSummary(request: Request, session_id: int):
    try:
        return await handleSessionSummary(request=request, session_id=session_id)
    except HTTPException:
        raise
    except Exception as e:
        raise CustomException(e, sys)
