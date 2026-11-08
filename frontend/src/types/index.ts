export type InspectionState =
  | 'ISSUE_DETECTED'
  | 'VERIFIED_NO_ISSUE'
  | 'BLOCKED_UNKNOWN'
  | 'NOT_TESTED';

export type PaymentState =
  | 'PENDING'
  | 'APPROVED'
  | 'CAPTURED'
  | 'DECLINED'
  | 'UNKNOWN';

export type CorrectionStatus =
  | 'PROPOSED'
  | 'APPROVED'
  | 'REJECTED'
  | 'APPLIED'
  | 'VERIFIED'
  | 'FAILED';

export interface HealthStatus {
  status: string;
  environment: string;
  version: string;
  database_connected: boolean;
  timestamp: string;
}

export interface ProductComparison {
  id: number;
  sku: string;
  title: string;
  description?: string | null;
  merchant_price: string;
  merchant_currency: string;
  storefront_price?: string | null;
  storefront_currency?: string | null;
  price_discrepancy?: string | null;
  has_discrepancy: boolean;
  is_comparable: boolean;
  comparability_reason?: string | null;
  availability: string;
  source_version: number;
  storefront_version?: number | null;
  updated_at: string;
}

export interface StorefrontProduct {
  id: number;
  sku: string;
  title: string;
  price: string;
  currency: string;
  availability: string;
  url_path: string;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface EvidenceItem {
  id: number;
  scan_id: number;
  evidence_type: string;
  field_name: string;
  expected_value?: string | null;
  observed_value?: string | null;
  source_url: string;
  observation_timestamp: string;
  content_hash?: string | null;
  status: 'MATCH' | 'MISMATCH' | 'BLOCKED' | string;
  details?: string | null;
  integrity_verified?: boolean;
  created_at: string;
}

export interface ScanSummary {
  id: number;
  product_id: number;
  sku: string;
  source_version: number;
  state: InspectionState;
  is_comparable: boolean;
  catalog_price?: string | null;
  observed_price?: string | null;
  currency?: string | null;
  discrepancy_amount?: string | null;
  idempotency_key?: string | null;
  created_at: string;
}

export interface ScanDetail extends ScanSummary {
  url: string;
  failure_reason?: string | null;
  correlation_id: string;
  comparability_reasons: string[];
  evidence_items: EvidenceItem[];
}

export type DiagnosisStatus = 'COMPLETED' | 'INSUFFICIENT_EVIDENCE' | 'FAILED';

export interface Diagnosis {
  id: number;
  scan_id: number;
  provider: string;
  model: string;
  prompt_version: string;
  status: DiagnosisStatus;
  summary: string;
  likely_causes: string[];
  supporting_evidence_ids: number[];
  missing_information: string[];
  recommended_actions: string[];
  confidence_explanation: string;
  is_advisory: boolean;
  created_at: string;
}

export type ProposalApprovalStatus =
  | 'PENDING_APPROVAL'
  | 'APPROVED'
  | 'REJECTED'
  | 'EXPIRED'
  | 'CANCELLED';

export type ProposalExecutionStatus =
  | 'NOT_STARTED'
  | 'IN_PROGRESS'
  | 'SUCCEEDED'
  | 'FAILED'
  | 'RECONCILIATION_REQUIRED';

export type ProposalPolicyStatus = 'VALID' | 'INVALID' | 'STALE' | 'BLOCKED';

export interface CorrectionProposal {
  id: number;
  scan_id: number;
  diagnosis_id?: number | null;
  product_id: number;
  sku: string;
  proposal_type: string;
  current_value: string;
  proposed_value: string;
  currency: string;
  reason: string;
  supporting_evidence_ids: number[];
  policy_validation_status: ProposalPolicyStatus;
  approval_status: ProposalApprovalStatus;
  execution_status: ProposalExecutionStatus;
  created_at: string;
  updated_at: string;
  expires_at: string;
  created_by: string;
  approved_by?: string | null;
  rejected_by?: string | null;
  rejection_reason?: string | null;
  executed_at?: string | null;
  expected_catalog_version: number;
  expected_storefront_version: number;
  idempotency_key?: string | null;
  execution_error?: string | null;
  execution_correlation_id?: string | null;
  is_expired?: boolean;
}

export interface ProposalHistoryItem {
  id: number;
  action: string;
  actor_id: string;
  actor_type: string;
  created_at: string;
  details?: string | null;
  before_state?: string | null;
  after_state?: string | null;
}

export interface CorrectionExecutionResult {
  proposal: CorrectionProposal;
  followup_scan?: ScanDetail | null;
}

export interface PreflightResult {
  passed: boolean;
  sku: string;
  catalog_price?: string | null;
  storefront_price?: string | null;
  currency?: string | null;
  scan_id?: number | null;
  scan_state?: string | null;
  blocking_reasons: string[];
  message: string;
}

export interface Order {
  id: number;
  order_id: string;
  paypal_order_id?: string | null;
  sku: string;
  unit_price: string;
  currency: string;
  quantity: number;
  total_amount: string;
  order_status: string;
  payment_status: string;
  preflight_passed: boolean;
  approve_url?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PaymentCapture {
  capture_id?: string | null;
  order_id: string;
  paypal_order_id?: string | null;
  status: string;
  amount: string;
  currency: string;
  fee_amount?: string | null;
  net_amount?: string | null;
  reconciliation_status: string;
  error_message?: string | null;
  created_at: string;
}

export interface ReconciliationResult {
  order_id: string;
  paypal_order_id?: string | null;
  order_status: string;
  payment_status: string;
  reconciliation_status: string;
  message: string;
}

export interface WebhookEvent {
  id: number;
  paypal_event_id: string;
  event_type: string;
  resource_type: string;
  status: string;
  summary?: string | null;
  created_at: string;
}

export interface StuckWebhookEvent {
  id: number;
  paypal_event_id: string;
  event_type: string;
  resource_type: string;
  status: string;
  attempt_count: number;
  max_attempts: number;
  error_category?: string | null;
  last_error?: string | null;
  last_attempt_at?: string | null;
  next_retry_at?: string | null;
  created_at: string;
}

export interface ReconciliationRecord {
  id: number;
  order_id: number;
  paypal_order_id?: string | null;
  paypal_capture_id?: string | null;
  outcome: string;
  previous_payment_status: string;
  new_payment_status: string;
  provider_status: string;
  details?: string | null;
  actor_id: string;
  actor_type: string;
  reconciled_at: string;
}

export interface WorkerHeartbeat {
  id: number;
  worker_id: string;
  worker_type: string;
  status: string;
  last_heartbeat_at: string;
  last_successful_run_at?: string | null;
  age_seconds?: number | null;
}

export interface OperationsOverview {
  system_status: 'HEALTHY' | 'DELAYED' | 'REQUIRES_ATTENTION' | 'DEAD_LETTERED' | 'RECONCILIATION_REQUIRED';
  webhook_counts: Record<string, number>;
  dead_letter_count: number;
  retryable_failure_count: number;
  pending_reconciliations_count: number;
  reconciliations_completed_count: number;
  active_workers_count: number;
  stale_workers_count: number;
  workers: WorkerHeartbeat[];
  recent_reconciliations: ReconciliationRecord[];
  stuck_webhooks: StuckWebhookEvent[];
}
