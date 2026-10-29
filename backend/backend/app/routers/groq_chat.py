"""Groq AI Assistant Router for Q-Transplant v2."""
from typing import Optional, List
from fastapi import APIRouter
from pydantic import BaseModel
from app.services.groq_assistant import chat_with_groq

router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])

class ChatMessage(BaseModel):
    role: str
    content: str

class GroqChatIn(BaseModel):
    message: str
    history: Optional[List[ChatMessage]] = []

@router.post("/chat")
def groq_chat_endpoint(body: GroqChatIn):
    """Processes user query via Groq AI Clinical Assistant."""
    hist = [{"role": item.role, "content": item.content} for item in body.history] if body.history else []
    reply = chat_with_groq(body.message, hist)
    return {"reply": reply}
