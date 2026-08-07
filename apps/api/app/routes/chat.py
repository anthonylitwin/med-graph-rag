import logging

from pydantic import BaseModel, ValidationError
from fastapi import APIRouter, HTTPException

from app.services.qa_service import answer_question, get_active_model_runtime

router = APIRouter()
logger = logging.getLogger(__name__)


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


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    logger.info("chat request received: chars=%s", len(request.message))
    try:
        result = answer_question(request.message)
        logger.info("chat request answered: sources=%s", len(result.get("sources", [])))
        return ChatResponse(**result)
    except ValidationError as exc:
        raise HTTPException(status_code=503, detail=f"Chat service unavailable: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Chat service unavailable: {exc}") from exc


@router.get("/model-options", response_model=ActiveModelRuntimeResponse)
def model_options() -> ActiveModelRuntimeResponse:
    return ActiveModelRuntimeResponse(**get_active_model_runtime())
