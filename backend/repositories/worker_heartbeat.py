import datetime
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.worker_heartbeat import WorkerHeartbeat


class WorkerHeartbeatRepository:
    """
    Persistence layer for background worker heartbeats and operational health status.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_worker_id(self, worker_id: str) -> Optional[WorkerHeartbeat]:
        stmt = select(WorkerHeartbeat).where(WorkerHeartbeat.worker_id == worker_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def upsert_heartbeat(
        self,
        worker_id: str,
        worker_type: str,
        status: str = "ACTIVE",
        metrics_json: Optional[str] = None,
        successful_run: bool = False,
    ) -> WorkerHeartbeat:
        now = datetime.datetime.now(datetime.timezone.utc)
        record = self.get_by_worker_id(worker_id)
        if not record:
            record = WorkerHeartbeat(
                worker_id=worker_id,
                worker_type=worker_type,
                status=status,
                last_heartbeat_at=now,
                last_successful_run_at=now if successful_run else None,
                metrics_json=metrics_json,
            )
            self.session.add(record)
        else:
            record.worker_type = worker_type
            record.status = status
            record.last_heartbeat_at = now
            if successful_run:
                record.last_successful_run_at = now
            if metrics_json is not None:
                record.metrics_json = metrics_json

        self.session.flush()
        return record

    def list_heartbeats(self) -> Sequence[WorkerHeartbeat]:
        stmt = select(WorkerHeartbeat).order_by(WorkerHeartbeat.worker_type.asc(), WorkerHeartbeat.worker_id.asc())
        return self.session.execute(stmt).scalars().all()
