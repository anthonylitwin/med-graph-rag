from pydantic import BaseModel
from fastapi import APIRouter

from app.services.graph_rag_service import answer_question

router = APIRouter()


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[dict]
    reasoningPath: list[dict]
    model: str


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    result = answer_question(request.message)
    return ChatResponse(**result)