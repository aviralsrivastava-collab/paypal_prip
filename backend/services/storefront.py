import json
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from backend.core.database import atomic_transaction
from backend.core.security import AuthenticatedActor, require_merchant_access
from backend.integrations.storefront.adapter import ControlledStorefrontAdapter
from backend.repositories.storefront import StorefrontRepository
from backend.schemas.audit import AuditEventCreate
from backend.schemas.storefront import StorefrontProductResponse, StorefrontUpdatePriceRequest
from backend.services.audit import AuditService


class StorefrontService:
    """
    Business service orchestrating interactions with the controlled demo storefront.
    Coordinates pricing updates, optimistic concurrency verification, and atomic audit logging.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = StorefrontRepository(session)
        self.adapter = ControlledStorefrontAdapter(session)

    def get_product(self, sku: str) -> Optional[StorefrontProductResponse]:
        """Fetch storefront product by SKU."""
        product = self.adapter.get_product(sku)
        if not product:
            return None
        return StorefrontProductResponse.from_orm_model(product)

    def update_price(
        self,
        sku: str,
        request: StorefrontUpdatePriceRequest,
        trusted_actor: Optional[AuthenticatedActor] = None,
    ) -> StorefrontProductResponse:
        """
        Updates the storefront product price atomically while recording an append-only audit event.
        Guarantees that the merchant-authorized catalog remains untouched.
        Derives actor identity strictly from server-side trusted authentication context,
        never trusting a client-supplied identity.
        """
        correlation_id = request.correlation_id or f"storefront-{uuid.uuid4()}"
        actor_id = trusted_actor.actor_id if trusted_actor else "system-operator"
        actor_type = trusted_actor.actor_type if trusted_actor else "merchant"

        details = request.reason or ""
        if request.actor_id and request.actor_id != actor_id:
            details += f" [Client actor_id '{request.actor_id}' overridden by trusted identity '{actor_id}']"

        with atomic_transaction(self.session):
            current_product = self.repository.get_by_sku(sku)
            if not current_product:
                raise ValueError(f"Storefront product with SKU '{sku}' not found.")

            if trusted_actor:
                require_merchant_access(trusted_actor, current_product.merchant_id)

            before_state = json.dumps(
                {
                    "price": str(current_product.price),
                    "currency": current_product.currency,
                    "version": current_product.version,
                }
            )

            updated = self.adapter.update_product_price(
                sku=sku,
                new_price=request.price,
                currency=request.currency,
                expected_version=request.expected_version,
            )

            after_state = json.dumps(
                {
                    "price": str(updated.price),
                    "currency": updated.currency,
                    "version": updated.version,
                }
            )

            AuditService.log_event(
                self.session,
                AuditEventCreate(
                    merchant_id=current_product.merchant_id,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    action="STOREFRONT_PRICE_UPDATED",
                    entity_type="storefront_product",
                    entity_id=sku,
                    approval_id=None,
                    correlation_id=correlation_id,
                    before_state=before_state,
                    after_state=after_state,
                    details=details.strip(),
                ),
            )

        return StorefrontProductResponse.from_orm_model(updated)
