from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.proposal import CorrectionProposal


class ProposalRepository:
    """
    Persistence layer for correction proposals.
    Provides atomic persistence, queries by ID, idempotency keys, and SKU.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, proposal: CorrectionProposal) -> CorrectionProposal:
        self.session.add(proposal)
        self.session.flush()
        return proposal

    def get_by_id(self, proposal_id: int) -> Optional[CorrectionProposal]:
        return self.session.get(CorrectionProposal, proposal_id)

    def get_by_idempotency_key(self, idempotency_key: str) -> Optional[CorrectionProposal]:
        stmt = select(CorrectionProposal).where(CorrectionProposal.idempotency_key == idempotency_key)
        return self.session.execute(stmt).scalar_one_or_none()

    def list_proposals(
        self,
        sku: Optional[str] = None,
        approval_status: Optional[str] = None,
        execution_status: Optional[str] = None,
        merchant_id: Optional[str] = None,
    ) -> Sequence[CorrectionProposal]:
        stmt = select(CorrectionProposal)
        if sku:
            stmt = stmt.where(CorrectionProposal.sku == sku)
        if approval_status:
            stmt = stmt.where(CorrectionProposal.approval_status == approval_status)
        if execution_status:
            stmt = stmt.where(CorrectionProposal.execution_status == execution_status)
        if merchant_id is not None:
            stmt = stmt.where(CorrectionProposal.merchant_id == merchant_id)
        stmt = stmt.order_by(CorrectionProposal.created_at.desc())
        return self.session.execute(stmt).scalars().all()

    def get_latest_by_sku(self, sku: str, merchant_id: Optional[str] = None) -> Optional[CorrectionProposal]:
        stmt = select(CorrectionProposal).where(CorrectionProposal.sku == sku)
        if merchant_id is not None:
            stmt = stmt.where(CorrectionProposal.merchant_id == merchant_id)
        stmt = stmt.order_by(CorrectionProposal.created_at.desc()).limit(1)
        return self.session.execute(stmt).scalar_one_or_none()

    def update(self, proposal: CorrectionProposal) -> CorrectionProposal:
        self.session.flush()
        return proposal
