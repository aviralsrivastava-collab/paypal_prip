from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.security import AuthenticatedActor, get_current_actor
from backend.integrations.ai.gemini_provider import GeminiAIProvider
from backend.repositories.merchant import MerchantRepository
from backend.services.catalog_intelligence import CatalogIntelligenceService
from backend.services.revenue_intelligence import RevenueIntelligenceService

router = APIRouter(prefix="/api/ai", tags=["AI Intelligence Engine"])


class ChatMessage(BaseModel):
    role: str = Field(..., description="'user', 'assistant', or 'system'")
    content: str = Field(..., min_length=1, max_length=2000)


class ChatRequest(BaseModel):
    messages: List[ChatMessage]


class ChatResponse(BaseModel):
    reply: str
    suggested_actions: List[str] = Field(default_factory=list)


@router.post("/chat", response_model=ChatResponse, summary="Conversational Merchant Assistant")
def chat_with_assistant(
    request: ChatRequest,
    actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> ChatResponse:
    merchant_repo = MerchantRepository(db)
    merchant = merchant_repo.get_by_id(actor.merchant_id) or merchant_repo.get_by_slug(actor.merchant_id)
    merchant_name = merchant.name if merchant else "Your Store"

    gemini = GeminiAIProvider()
    context = {
        "merchant_id": actor.merchant_id,
        "merchant_name": merchant_name,
        "actor_role": actor.role,
    }

    raw_messages = [{"role": m.role, "content": m.content} for m in request.messages]
    reply = gemini.chat_assist(raw_messages, merchant_context=context)

    suggested = [
        "Review active price discrepancies",
        "Inspect catalog quality scores",
        "View verified PayPal captured revenue",
    ]

    return ChatResponse(reply=reply, suggested_actions=suggested)


@router.get("/catalog-intelligence", summary="Catalog Health & Quality Scoring")
def get_catalog_intelligence(
    actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    service = CatalogIntelligenceService(db)
    return service.analyze_catalog(merchant_id=actor.merchant_id)


@router.get("/revenue-intelligence", summary="Revenue Protection & Leakage Analytics")
def get_revenue_intelligence(
    actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    service = RevenueIntelligenceService(db)
    return service.get_revenue_metrics(merchant_id=actor.merchant_id)
