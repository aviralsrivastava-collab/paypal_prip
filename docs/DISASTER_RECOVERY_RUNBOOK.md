# PRIP Disaster Recovery Runbook

## 1. Objectives and SLAs

- **RTO (Recovery Time Objective)**: 30 minutes from incident declaration to restored service.
- **RPO (Recovery Point Objective)**: 15 minutes maximum permissible data loss.
- **Target Architecture**: PostgreSQL database snapshots, append-only immutable audit log, and idempotent distributed worker processing.

---

## 2. Database Backup & Restore Procedures

### Automated Database Backup
Execute hourly scheduled snapshots of the primary PostgreSQL database:
```bash
docker exec -t prip-db pg_dump -U prip -d prip_db -F c -b -v -f /var/lib/postgresql/data/backup_$(date +%Y%m%d_%H%M%S).dump
```

### Full Database Restoration Procedure
1. Stop backend and worker containers to avoid concurrent writes:
   ```bash
   docker compose -f infra/docker-compose.yml stop backend worker
   ```
2. Drop and recreate database:
   ```bash
   docker exec -i prip-db psql -U prip -c "DROP DATABASE prip_db;"
   docker exec -i prip-db psql -U prip -c "CREATE DATABASE prip_db;"
   ```
3. Restore from verified snapshot:
   ```bash
   docker exec -i prip-db pg_restore -U prip -d prip_db -v /var/lib/postgresql/data/backup_TARGET.dump
   ```
4. Verify schema revision:
   ```bash
   docker compose -f infra/docker-compose.yml run --rm migration alembic current
   ```
5. Restart application services:
   ```bash
   docker compose -f infra/docker-compose.yml start backend worker
   ```

---

## 3. Worker Failure and Lease Recovery

If a worker node crashes mid-execution:
1. **Automatic Lease Expiration**: The worker holds a 60-second lease (`processing_lease_expires_at`). Once expired, any active worker automatically reclaims the event during `worker.tick()`.
2. **Crash Recovery Test**:
   ```bash
   # Inspect stuck leases
   docker exec -it prip-backend python -c "from backend.core.database import SessionLocal; from backend.repositories.webhook import WebhookEventRepository; s=SessionLocal(); print(len(WebhookEventRepository(s).list_failed_or_stuck_events())); s.close()"
   ```
3. **Dead-Letter Replay**:
   Events that exceeded maximum attempts (5) transition to `DEAD_LETTER`.
   Trigger operator replay via API:
   ```bash
   curl -X POST http://localhost:8000/api/operations/webhooks/reprocess-failed \
     -H "Authorization: Bearer <ADMIN_TOKEN>"
   ```

---

## 4. Payment Ambiguity & PayPal Reconciliation

If network timeouts occur between PRIP and PayPal during capture:
1. The order enters `payment_status = "UNKNOWN"`.
2. Automatic background reconciliation polls PayPal Orders v2 endpoint to discover whether PayPal actually authorized/captured the transaction.
3. If capture completed on PayPal, the order status transitions to `CAPTURED`, inventory reservation commits, and audit logs record the reconciliation.
4. If capture never occurred on PayPal, the order transitions to `FAILED`, demo inventory is released, and customer is prompted to retry.
