import time
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.core.metrics import get_metrics_collector
from backend.repositories.reconciliation import PaymentReconciliationRepository
from backend.repositories.webhook import WebhookEventRepository
from backend.repositories.worker_heartbeat import WorkerHeartbeatRepository
from backend.schemas.health import HealthResponse

settings = get_settings()


class HealthService:
    @staticmethod
    def check_health(session: Session) -> HealthResponse:
        database_connected = False
        db_latency_ms = 0.0
        now = datetime.now(timezone.utc)

        # 1. Database dependency check with latency measurement
        t0 = time.perf_counter()
        try:
            session.execute(text("SELECT 1"))
            database_connected = True
            db_latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        except Exception:
            database_connected = False

        dependencies: Dict[str, Any] = {
            "database": {
                "status": "healthy" if database_connected else "down",
                "latency_ms": db_latency_ms if database_connected else None,
            },
            "paypal_sandbox": {
                "status": "configured",
                "environment": settings.paypal_environment,
                "base_url": settings.paypal_base_url,
                "webhook_configured": bool(settings.paypal_webhook_id),
            },
        }

        # 2. Worker heartbeat & operational visibility (only if database connected)
        worker_summary: Dict[str, Any] = {
            "status": "idle",
            "active_workers": 0,
            "stale_workers": 0,
            "workers": [],
        }
        operational_metrics: Dict[str, Any] = {
            "webhook_counts": {},
            "pending_reconciliations": 0,
            "reconciliation_counts": {},
            "metrics": get_metrics_collector().get_metrics(),
        }

        if database_connected:
            try:
                # Heartbeats
                heartbeat_repo = WorkerHeartbeatRepository(session)
                heartbeats = heartbeat_repo.list_heartbeats()
                active_count = 0
                stale_count = 0
                workers_data = []

                for hb in heartbeats:
                    hb_time = hb.last_heartbeat_at
                    if hb_time.tzinfo is None:
                        hb_time = hb_time.replace(tzinfo=timezone.utc)
                    age_seconds = (now - hb_time).total_seconds()
                    is_stale = age_seconds > 120.0
                    if is_stale:
                        stale_count += 1
                        hb_status = "STALE"
                    else:
                        active_count += 1
                        hb_status = hb.status

                    workers_data.append({
                        "worker_id": hb.worker_id,
                        "worker_type": hb.worker_type,
                        "status": hb_status,
                        "last_heartbeat_at": hb.last_heartbeat_at.isoformat(),
                        "age_seconds": round(age_seconds, 1),
                        "last_successful_run_at": hb.last_successful_run_at.isoformat() if hb.last_successful_run_at else None,
                    })

                worker_summary = {
                    "status": "degraded" if stale_count > 0 else ("active" if active_count > 0 else "idle"),
                    "active_workers": active_count,
                    "stale_workers": stale_count,
                    "workers": workers_data,
                }

                # Webhook counts
                wh_repo = WebhookEventRepository(session)
                operational_metrics["webhook_counts"] = wh_repo.get_counts_by_status()

                # Reconciliation counts
                rec_repo = PaymentReconciliationRepository(session)
                pending_recons = rec_repo.list_orders_requiring_reconciliation()
                operational_metrics["pending_reconciliations"] = len(pending_recons)
                operational_metrics["reconciliation_counts"] = rec_repo.get_counts()

            except Exception:
                # Non-fatal for health endpoint
                pass

        # Determine overall application status
        if not database_connected:
            status = "degraded"
        elif worker_summary.get("stale_workers", 0) > 0:
            status = "degraded"
        else:
            status = "healthy"

        return HealthResponse(
            status=status,
            environment=settings.app_env,
            version=settings.app_version,
            database_connected=database_connected,
            timestamp=now,
            dependencies=dependencies,
            worker_health=worker_summary,
            operational_metrics=operational_metrics,
        )
