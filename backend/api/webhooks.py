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

_PAYPAL_SIGNATURE_HEADERS = (
    "paypal-transmission-id",
    "paypal-transmission-time",
    "paypal-cert-url",
    "paypal-auth-algo",
    "paypal-transmission-sig",
)


def _paypal_signature_header_availability(headers: Dict[str, str]) -> Dict[str, bool]:
    """Return non-empty availability flags without exposing signature header values."""
    normalized = {
        name.lower(): (value or "").strip()
        for name, value in headers.items()
    }
    return {
        header: bool(normalized.get(header))
        for header in _PAYPAL_SIGNATURE_HEADERS
    }


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

    availability = _paypal_signature_header_availability(headers)
    logger.info("PayPal webhook signature header availability: %s", availability)

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
    if not isinstance(current_actor, AuthenticatedActor):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Merchant authentication required to list webhook events.",
        )
    service = WebhookService(db)
    events = service.webhook_repo.list_events(limit=50)
    return [WebhookEventResponse.model_validate(e) for e in events]
