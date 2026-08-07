import os
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from app.services.qa_service import answer_question, get_active_model_runtime

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    modelProfile: str | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[dict]
    reasoningPath: list[dict]
    model: str
    provider: str
    modelProfile: str
    confidence: float | None = None
    abstained: bool | None = None


class ModelOption(BaseModel):
    name: str
    label: str
    description: str
    qa_provider: str
    qa_model: str
    qa_retriever: str
    extractor_provider: str
    extractor_model: str
    entity_model: str = ""


class ActiveModelRuntimeResponse(BaseModel):
    activeProfile: ModelOption
    graphRunId: str = ""


def _chat_request_timeout_seconds() -> int:
    return int(os.getenv("APP_CHAT_REQUEST_TIMEOUT_SECONDS", "35"))


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    timeout_seconds = _chat_request_timeout_seconds()
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(answer_question, request.message)
    try:
        result = future.result(timeout=timeout_seconds)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FutureTimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=f"Chat request timed out after {timeout_seconds} seconds.",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Chat service unavailable: {exc}") from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    return ChatResponse(**result)


@router.get("/model-options", response_model=ActiveModelRuntimeResponse)
def model_options() -> ActiveModelRuntimeResponse:
    return ActiveModelRuntimeResponse(**get_active_model_runtime())
