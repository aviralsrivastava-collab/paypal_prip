from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.diagnosis import Diagnosis


class DiagnosisRepository:
    """
    Repository for persisting and querying advisory AI diagnosis records.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, diagnosis: Diagnosis) -> Diagnosis:
        self.session.add(diagnosis)
        self.session.flush()
        return diagnosis

    def get_by_id(self, diagnosis_id: int, include_quarantined: bool = False) -> Optional[Diagnosis]:
        diagnosis = self.session.get(Diagnosis, diagnosis_id)
        if diagnosis and diagnosis.merchant_id == "QUARANTINED_ORPHAN" and not include_quarantined:
            return None
        return diagnosis

    def list_by_scan_id(self, scan_id: int, include_quarantined: bool = False) -> Sequence[Diagnosis]:
        stmt = select(Diagnosis).where(Diagnosis.scan_id == scan_id)
        if not include_quarantined:
            stmt = stmt.where(Diagnosis.merchant_id != "QUARANTINED_ORPHAN")
        stmt = stmt.order_by(Diagnosis.created_at.desc())
        return self.session.execute(stmt).scalars().all()

    def get_latest_by_scan_id(self, scan_id: int, include_quarantined: bool = False) -> Optional[Diagnosis]:
        stmt = select(Diagnosis).where(Diagnosis.scan_id == scan_id)
        if not include_quarantined:
            stmt = stmt.where(Diagnosis.merchant_id != "QUARANTINED_ORPHAN")
        stmt = stmt.order_by(Diagnosis.created_at.desc()).limit(1)
        return self.session.execute(stmt).scalar_one_or_none()
