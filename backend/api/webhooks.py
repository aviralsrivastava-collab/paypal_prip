import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.security import AuthenticatedActor, get_current_actor
from backend.schemas.webhook import WebhookEventResponse
from backend.services.webhook import WebhookService

router = APIRouter(prefix="/api/webhooks", tags=["Webhooks"])
logger = logging.getLogger(__name__)


@router.post(
    "/paypal",
    summary="Receive and process incoming PayPal webhook notifications",
)
async def paypal_webhook_listener(
    request: Request,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Receives incoming PayPal webhook events.
    Preserves exact raw body bytes for cryptographic signature verification,
    deduplicates on paypal_event_id, and triggers state transitions.
    """
    raw_bytes = await request.body()
    raw_body = raw_bytes.decode("utf-8")
    headers = dict(request.headers)

    lower_header_keys = {k.lower() for k in headers}
    presence = {
        h: (h in lower_header_keys)
        for h in (
            "paypal-transmission-id",
            "paypal-transmission-time",
            "paypal-cert-url",
            "paypal-auth-algo",
            "paypal-transmission-sig",
        )
    }
    logger.info("PayPal webhook header presence: %s", presence)

    service = WebhookService(db)
    try:
        event_resp = service.process_webhook(headers=headers, raw_body=raw_body)
        return {
            "status": "ok",
            "event_id": event_resp.paypal_event_id,
            "event_type": event_resp.event_type,
            "processing_status": event_resp.status,
        }
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get(
    "/events",
    response_model=List[WebhookEventResponse],
    summary="List recent webhook events",
)
def list_webhook_events(
    current_actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> List[WebhookEventResponse]:
    service = WebhookService(db)
    events = service.webhook_repo.list_events(limit=50)
    return [WebhookEventResponse.model_validate(e) for e in events]
