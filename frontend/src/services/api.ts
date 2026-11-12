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
  UserProfile,
  MerchantWorkspace,
  Membership,
  CatalogIntelligence,
  RevenueIntelligence,
  ChatMessage,
  ChatResponse,
} from '../types';

export class ApiClient {
  public static getBaseUrl(): string {
    const envUrl = import.meta.env.VITE_API_URL;
    if (envUrl && typeof envUrl === 'string') {
      const clean = envUrl.trim().replace(/\/+$/, '');
      if (!clean) return '/api';
      return clean.endsWith('/api') ? clean : `${clean}/api`;
    }
    return '/api';
  }

  private static get baseUrl(): string {
    return ApiClient.getBaseUrl();
  }

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
    returnUrl?: string,
    cancelUrl?: string,
    idempotencyKey?: string
  ): Promise<Order> {
    const defaultReturn = typeof window !== 'undefined' ? `${window.location.origin}/checkout?status=approved` : undefined;
    const defaultCancel = typeof window !== 'undefined' ? `${window.location.origin}/checkout?status=cancelled` : undefined;
    const res = await fetch(`${this.baseUrl}/checkout/orders`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sku,
        quantity,
        return_url: returnUrl || defaultReturn,
        cancel_url: cancelUrl || defaultCancel,
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

  // --- Multi-Tenant & Identity Methods ---
  public static getActiveMerchantId(): string | null {
    return localStorage.getItem('prip_active_merchant_id');
  }

  public static setActiveMerchantId(merchantId: string | null): void {
    if (merchantId) {
      localStorage.setItem('prip_active_merchant_id', merchantId);
    } else {
      localStorage.removeItem('prip_active_merchant_id');
    }
  }

  public static getAuthHeaders(): Record<string, string> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    const activeMerchant = this.getActiveMerchantId();
    if (activeMerchant) {
      headers['X-Merchant-ID'] = activeMerchant;
    }
    return headers;
  }

  public static async getProfile(): Promise<UserProfile> {
    const res = await fetch(`${this.baseUrl}/auth/me`, {
      headers: this.getAuthHeaders(),
    });
    if (!res.ok) {
      throw new Error(`Failed to fetch user profile: ${res.status}`);
    }
    return res.json();
  }

  public static async createWorkspace(name: string, slug: string): Promise<MerchantWorkspace> {
    const res = await fetch(`${this.baseUrl}/auth/merchants`, {
      method: 'POST',
      headers: this.getAuthHeaders(),
      body: JSON.stringify({ name, slug }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to create merchant workspace: ${res.status}`);
    }
    return res.json();
  }

  public static async switchTenant(merchantId: string): Promise<{ active_merchant_id: string; active_merchant_name: string; active_role: string }> {
    const res = await fetch(`${this.baseUrl}/auth/switch-tenant`, {
      method: 'POST',
      headers: this.getAuthHeaders(),
      body: JSON.stringify({ merchant_id: merchantId }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to switch workspace: ${res.status}`);
    }
    const data = await res.json();
    this.setActiveMerchantId(data.active_merchant_id);
    return data;
  }

  public static async getMembers(): Promise<Membership[]> {
    const res = await fetch(`${this.baseUrl}/auth/members`, {
      headers: this.getAuthHeaders(),
    });
    if (!res.ok) {
      throw new Error(`Failed to fetch members: ${res.status}`);
    }
    return res.json();
  }

  public static async inviteMember(email: string, role: string): Promise<Membership> {
    const res = await fetch(`${this.baseUrl}/auth/members`, {
      method: 'POST',
      headers: this.getAuthHeaders(),
      body: JSON.stringify({ email, role }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to invite member: ${res.status}`);
    }
    return res.json();
  }

  public static async removeMember(userId: string): Promise<void> {
    const res = await fetch(`${this.baseUrl}/auth/members/${encodeURIComponent(userId)}`, {
      method: 'DELETE',
      headers: this.getAuthHeaders(),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to remove member: ${res.status}`);
    }
  }

  // --- Catalog CRUD Methods ---
  public static async createProduct(product: {
    sku: string;
    title: string;
    price: number | string;
    currency?: string;
    description?: string;
    storefront_price?: number | string;
  }): Promise<ProductComparison> {
    const res = await fetch(`${this.baseUrl}/products`, {
      method: 'POST',
      headers: this.getAuthHeaders(),
      body: JSON.stringify({
        sku: product.sku,
        title: product.title,
        price: product.price,
        currency: product.currency || 'USD',
        description: product.description || null,
        storefront_price: product.storefront_price || null,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to create product: ${res.status}`);
    }
    return res.json();
  }

  public static async updateProduct(
    id: number,
    product: { title?: string; description?: string; price?: number | string; currency?: string }
  ): Promise<ProductComparison> {
    const res = await fetch(`${this.baseUrl}/products/${id}`, {
      method: 'PUT',
      headers: this.getAuthHeaders(),
      body: JSON.stringify(product),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to update product: ${res.status}`);
    }
    return res.json();
  }

  public static async deleteProduct(id: number): Promise<void> {
    const res = await fetch(`${this.baseUrl}/products/${id}`, {
      method: 'DELETE',
      headers: this.getAuthHeaders(),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to delete product: ${res.status}`);
    }
  }

  public static async updateStorefrontPrice(
    sku: string,
    price: number | string,
    currency = 'USD'
  ): Promise<ProductComparison> {
    const res = await fetch(`${this.baseUrl}/products/sku/${encodeURIComponent(sku)}/storefront-price`, {
      method: 'PUT',
      headers: this.getAuthHeaders(),
      body: JSON.stringify({ price, currency }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to update storefront price: ${res.status}`);
    }
    return res.json();
  }

  // --- AI Intelligence & Assistant Methods ---
  public static async getCatalogIntelligence(): Promise<CatalogIntelligence> {
    const res = await fetch(`${this.baseUrl}/ai/catalog-intelligence`, {
      headers: this.getAuthHeaders(),
    });
    if (!res.ok) {
      throw new Error(`Failed to fetch catalog intelligence: ${res.status}`);
    }
    return res.json();
  }

  public static async getRevenueIntelligence(): Promise<RevenueIntelligence> {
    const res = await fetch(`${this.baseUrl}/ai/revenue-intelligence`, {
      headers: this.getAuthHeaders(),
    });
    if (!res.ok) {
      throw new Error(`Failed to fetch revenue intelligence: ${res.status}`);
    }
    return res.json();
  }

  public static async sendChatMessage(messages: ChatMessage[]): Promise<ChatResponse> {
    const res = await fetch(`${this.baseUrl}/ai/chat`, {
      method: 'POST',
      headers: this.getAuthHeaders(),
      body: JSON.stringify({ messages }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Chat request failed: ${res.status}`);
    }
    return res.json();
  }
}
