from pydantic import BaseModel
from fastapi import APIRouter

router = APIRouter()

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    answer: str
    sources: list[dict]
    reasoning_path: list[dict]
    model: str

@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    return ChatResponse(
        answer=f"Hello from MedGraphRag.  You asked {request.message}",
        sources=[],
        reasoning_path=[],
        model="mock-baseline-v0"
    )
