import {
  CorrectionExecutionResult,
  CorrectionProposal,
  Diagnosis,
  EvidenceItem,
  HealthStatus,
  Order,
  PaymentCapture,
  PreflightResult,
  ProductComparison,
  ProposalHistoryItem,
  ReconciliationRecord,
  ReconciliationResult,
  ScanDetail,
  ScanSummary,
  StuckWebhookEvent,
  WebhookEvent,
  WorkerHeartbeat,
  OperationsOverview,
} from '../types';

export class ApiClient {
  private static getBaseUrl(): string {
    const envUrl =
      (import.meta as any).env?.VITE_API_URL ||
      (typeof process !== 'undefined' ? (process as any).env?.VITE_API_URL : undefined);
    if (envUrl && typeof envUrl === 'string') {
      const clean = envUrl.trim().replace(/\/+$/, '');
      if (!clean) return '/api';
      return clean.endsWith('/api') ? clean : `${clean}/api`;
    }
    return '/api';
  }

  private static baseUrl = ApiClient.getBaseUrl();

  public static async getHealth(): Promise<HealthStatus> {
    const res = await fetch(`${this.baseUrl}/health`);
    if (!res.ok) {
      throw new Error(`Health check failed with status: ${res.status}`);
    }
    return res.json();
  }

  public static async getProducts(): Promise<ProductComparison[]> {
    const res = await fetch(`${this.baseUrl}/products`);
    if (!res.ok) {
      throw new Error(`Failed to fetch catalog products: ${res.status}`);
    }
    return res.json();
  }

  public static async seedCatalog(reset = false): Promise<{ status: string; discrepancy: string }> {
    const res = await fetch(`${this.baseUrl}/products/seed?reset=${reset}`, {
      method: 'POST',
    });
    if (!res.ok) {
      throw new Error(`Failed to seed catalog: ${res.status}`);
    }
    return res.json();
  }

  public static async triggerScan(sku: string, simulatedScenario?: string, idempotencyKey?: string): Promise<ScanDetail> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (idempotencyKey) {
      headers['Idempotency-Key'] = idempotencyKey;
    }
    const res = await fetch(`${this.baseUrl}/scans`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        sku,
        simulated_scenario: simulatedScenario || null,
        idempotency_key: idempotencyKey || null,
      }),
    });
    if (!res.ok) {
      throw new Error(`Failed to trigger inspection: ${res.status}`);
    }
    return res.json();
  }

  public static async getScan(scanId: number): Promise<ScanDetail> {
    const res = await fetch(`${this.baseUrl}/scans/${scanId}`);
    if (!res.ok) {
      throw new Error(`Failed to fetch scan detail: ${res.status}`);
    }
    return res.json();
  }

  public static async getProductScans(sku: string): Promise<ScanSummary[]> {
    const res = await fetch(`${this.baseUrl}/scans/product/${sku}`);
    if (!res.ok) {
      throw new Error(`Failed to fetch scans for product: ${res.status}`);
    }
    return res.json();
  }

  public static async getScanEvidence(scanId: number): Promise<EvidenceItem[]> {
    const res = await fetch(`${this.baseUrl}/scans/${scanId}/evidence`);
    if (!res.ok) {
      throw new Error(`Failed to fetch evidence for scan: ${res.status}`);
    }
    return res.json();
  }

  public static async triggerDiagnosis(scanId: number, simulatedFailure?: string): Promise<Diagnosis> {
    const res = await fetch(`${this.baseUrl}/diagnoses/scan/${scanId}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        simulated_failure: simulatedFailure || null,
      }),
    });
    if (!res.ok) {
      throw new Error(`Failed to generate diagnosis: ${res.status}`);
    }
    return res.json();
  }

  public static async getScanDiagnoses(scanId: number): Promise<Diagnosis[]> {
    const res = await fetch(`${this.baseUrl}/diagnoses/scan/${scanId}`);
    if (!res.ok) {
      throw new Error(`Failed to fetch scan diagnoses: ${res.status}`);
    }
    return res.json();
  }

  public static async getDiagnosis(diagnosisId: number): Promise<Diagnosis> {
    const res = await fetch(`${this.baseUrl}/diagnoses/${diagnosisId}`);
    if (!res.ok) {
      throw new Error(`Failed to fetch diagnosis: ${res.status}`);
    }
    return res.json();
  }

  public static async getProposals(
    sku?: string,
    approvalStatus?: string,
    executionStatus?: string
  ): Promise<CorrectionProposal[]> {
    const params = new URLSearchParams();
    if (sku) params.append('sku', sku);
    if (approvalStatus) params.append('approval_status', approvalStatus);
    if (executionStatus) params.append('execution_status', executionStatus);
    const queryString = params.toString() ? `?${params.toString()}` : '';
    const res = await fetch(`${this.baseUrl}/corrections/proposals${queryString}`);
    if (!res.ok) {
      throw new Error(`Failed to fetch proposals: ${res.status}`);
    }
    return res.json();
  }

  public static async getProposal(proposalId: number): Promise<CorrectionProposal> {
    const res = await fetch(`${this.baseUrl}/corrections/proposals/${proposalId}`);
    if (!res.ok) {
      throw new Error(`Failed to fetch proposal #${proposalId}: ${res.status}`);
    }
    return res.json();
  }

  public static async createProposal(data: {
    scan_id: number;
    sku: string;
    proposed_value: string;
    currency: string;
    reason: string;
    supporting_evidence_ids: number[];
    idempotency_key?: string;
  }): Promise<CorrectionProposal> {
    const res = await fetch(`${this.baseUrl}/corrections/proposals`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to create proposal: ${res.status}`);
    }
    return res.json();
  }

  public static async approveProposal(
    proposalId: number,
    reason?: string
  ): Promise<CorrectionProposal> {
    const res = await fetch(`${this.baseUrl}/corrections/proposals/${proposalId}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: reason || null }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to approve proposal: ${res.status}`);
    }
    return res.json();
  }

  public static async rejectProposal(
    proposalId: number,
    reason: string
  ): Promise<CorrectionProposal> {
    const res = await fetch(`${this.baseUrl}/corrections/proposals/${proposalId}/reject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to reject proposal: ${res.status}`);
    }
    return res.json();
  }

  public static async cancelProposal(
    proposalId: number,
    reason?: string
  ): Promise<CorrectionProposal> {
    const res = await fetch(`${this.baseUrl}/corrections/proposals/${proposalId}/cancel`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: reason || null }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to cancel proposal: ${res.status}`);
    }
    return res.json();
  }

  public static async executeProposal(
    proposalId: number,
    options?: {
      idempotency_key?: string;
      simulate_timeout?: boolean;
      simulate_storefront_error?: boolean;
    }
  ): Promise<CorrectionExecutionResult> {
    const res = await fetch(`${this.baseUrl}/corrections/proposals/${proposalId}/execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(options || {}),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to execute correction: ${res.status}`);
    }
    return res.json();
  }

  public static async reconcileProposal(proposalId: number): Promise<CorrectionExecutionResult> {
    const res = await fetch(`${this.baseUrl}/corrections/proposals/${proposalId}/reconcile`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to reconcile proposal: ${res.status}`);
    }
    return res.json();
  }

  public static async getProposalHistory(proposalId: number): Promise<ProposalHistoryItem[]> {
    const res = await fetch(`${this.baseUrl}/corrections/proposals/${proposalId}/history`);
    if (!res.ok) {
      throw new Error(`Failed to fetch history for proposal: ${res.status}`);
    }
    return res.json();
  }

  public static async checkPreflight(sku: string): Promise<PreflightResult> {
    const res = await fetch(`${this.baseUrl}/checkout/preflight`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sku }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Preflight check failed: ${res.status}`);
    }
    return res.json();
  }

  public static async createOrder(
    sku: string,
    quantity = 1,
    idempotencyKey?: string
  ): Promise<Order> {
    const res = await fetch(`${this.baseUrl}/checkout/orders`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sku,
        quantity,
        idempotency_key: idempotencyKey || null,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to create order: ${res.status}`);
    }
    return res.json();
  }

  public static async captureOrder(
    orderId: string,
    options?: { simulateTimeout?: boolean; simulateDecline?: boolean }
  ): Promise<PaymentCapture> {
    const res = await fetch(`${this.baseUrl}/checkout/orders/${orderId}/capture`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        order_id: orderId,
        simulate_timeout: options?.simulateTimeout || false,
        simulate_decline: options?.simulateDecline || false,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to capture order: ${res.status}`);
    }
    return res.json();
  }

  public static async reconcileOrder(orderId: string): Promise<ReconciliationResult> {
    const res = await fetch(`${this.baseUrl}/checkout/orders/${orderId}/reconcile`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ order_id: orderId }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to reconcile order: ${res.status}`);
    }
    return res.json();
  }

  public static async getOrders(): Promise<Order[]> {
    const res = await fetch(`${this.baseUrl}/checkout/orders`);
    if (!res.ok) {
      throw new Error(`Failed to fetch orders: ${res.status}`);
    }
    return res.json();
  }

  public static async getOrder(orderId: string): Promise<Order> {
    const res = await fetch(`${this.baseUrl}/checkout/orders/${orderId}`);
    if (!res.ok) {
      throw new Error(`Failed to fetch order: ${res.status}`);
    }
    return res.json();
  }

  public static async getWebhookEvents(): Promise<WebhookEvent[]> {
    const res = await fetch(`${this.baseUrl}/webhooks/events`);
    if (!res.ok) {
      throw new Error(`Failed to fetch webhook events: ${res.status}`);
    }
    return res.json();
  }

  public static async getOperationsOverview(): Promise<OperationsOverview> {
    const res = await fetch(`${this.baseUrl}/operations/overview`);
    if (!res.ok) {
      throw new Error(`Failed to fetch operations overview: ${res.status}`);
    }
    return res.json();
  }

  public static async getStuckWebhooks(): Promise<StuckWebhookEvent[]> {
    const res = await fetch(`${this.baseUrl}/operations/webhooks/stuck`);
    if (!res.ok) {
      throw new Error(`Failed to fetch stuck webhooks: ${res.status}`);
    }
    return res.json();
  }

  public static async replayWebhook(eventId: number): Promise<{ id: number; status: string; message: string }> {
    const res = await fetch(`${this.baseUrl}/operations/webhooks/${eventId}/replay`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to replay webhook: ${res.status}`);
    }
    return res.json();
  }

  public static async getPendingReconciliations(): Promise<Order[]> {
    const res = await fetch(`${this.baseUrl}/operations/reconciliations/pending`);
    if (!res.ok) {
      throw new Error(`Failed to fetch pending reconciliations: ${res.status}`);
    }
    return res.json();
  }

  public static async getReconciliationHistory(): Promise<ReconciliationRecord[]> {
    const res = await fetch(`${this.baseUrl}/operations/reconciliations/history`);
    if (!res.ok) {
      throw new Error(`Failed to fetch reconciliation history: ${res.status}`);
    }
    return res.json();
  }

  public static async triggerReconciliation(orderId?: string): Promise<{ reconciled_count: number; results: any[] }> {
    const res = await fetch(`${this.baseUrl}/operations/reconciliations/trigger`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ order_id: orderId || null }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to trigger reconciliation: ${res.status}`);
    }
    return res.json();
  }

  public static async getWorkers(): Promise<WorkerHeartbeat[]> {
    const res = await fetch(`${this.baseUrl}/operations/workers`);
    if (!res.ok) {
      throw new Error(`Failed to fetch workers: ${res.status}`);
    }
    return res.json();
  }

  public static async triggerWorkerTick(): Promise<{ status: string; processed_events: number }> {
    const res = await fetch(`${this.baseUrl}/operations/workers/tick`, {
      method: 'POST',
    });
    if (!res.ok) {
      throw new Error(`Failed to trigger worker tick: ${res.status}`);
    }
    return res.json();
  }
}
