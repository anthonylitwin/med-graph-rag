from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from app.services.qa_service import answer_question, get_model_options

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


class ModelOptionsResponse(BaseModel):
    defaultProfile: str
    profiles: list[ModelOption]


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    try:
        result = answer_question(request.message, request.modelProfile)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ChatResponse(**result)


@router.get("/model-options", response_model=ModelOptionsResponse)
def model_options() -> ModelOptionsResponse:
    return ModelOptionsResponse(**get_model_options())
