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


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    try:
        result = answer_question(request.message)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ChatResponse(**result)


@router.get("/model-options", response_model=ActiveModelRuntimeResponse)
def model_options() -> ActiveModelRuntimeResponse:
    return ActiveModelRuntimeResponse(**get_active_model_runtime())
