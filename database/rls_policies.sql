-- =============================================================================
-- PRIP (PayPal Revenue Intelligence Platform) - Multi-Tenant RLS Policies
-- Target: Supabase / PostgreSQL
-- =============================================================================

-- Enable Row Level Security (RLS) on all multi-tenant tables
ALTER TABLE merchants ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE merchant_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE products ENABLE ROW LEVEL SECURITY;
ALTER TABLE storefront_products ENABLE ROW LEVEL SECURITY;
ALTER TABLE storefront_scans ENABLE ROW LEVEL SECURITY;
ALTER TABLE diagnoses ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE correction_proposals ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE payment_captures ENABLE ROW LEVEL SECURITY;
ALTER TABLE inventory_reservations ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;

-- -----------------------------------------------------------------------------
-- Helper function to extract authenticated user's internal ID from JWT sub/email
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION auth.prip_user_id()
RETURNS text AS $$
  SELECT coalesce(
    current_setting('request.jwt.claims', true)::json->>'sub',
    current_setting('app.current_user_id', true)
  );
$$ LANGUAGE sql STABLE;

-- -----------------------------------------------------------------------------
-- Helper function to check if the caller is an active member of target merchant
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION auth.is_merchant_member(target_merchant_id text)
RETURNS boolean AS $$
  SELECT EXISTS (
    SELECT 1 FROM merchant_memberships mm
    JOIN users u ON u.id = mm.user_id
    WHERE mm.merchant_id = target_merchant_id
      AND mm.is_active = true
      AND (u.sub = auth.prip_user_id() OR u.id = auth.prip_user_id())
  );
$$ LANGUAGE sql STABLE;

-- -----------------------------------------------------------------------------
-- Helper function to check minimum membership role
-- Hierarchy: VIEWER < MANAGER < ADMIN < OWNER
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION auth.has_merchant_role(target_merchant_id text, min_role text)
RETURNS boolean AS $$
  SELECT EXISTS (
    SELECT 1 FROM merchant_memberships mm
    JOIN users u ON u.id = mm.user_id
    WHERE mm.merchant_id = target_merchant_id
      AND mm.is_active = true
      AND (u.sub = auth.prip_user_id() OR u.id = auth.prip_user_id())
      AND (
        (min_role = 'VIEWER' AND mm.role IN ('VIEWER', 'MANAGER', 'ADMIN', 'OWNER')) OR
        (min_role = 'MANAGER' AND mm.role IN ('MANAGER', 'ADMIN', 'OWNER')) OR
        (min_role = 'ADMIN' AND mm.role IN ('ADMIN', 'OWNER')) OR
        (min_role = 'OWNER' AND mm.role = 'OWNER')
      )
  );
$$ LANGUAGE sql STABLE;

-- -----------------------------------------------------------------------------
-- 1. Merchants Table Policies
-- -----------------------------------------------------------------------------
CREATE POLICY merchant_read_policy ON merchants
  FOR SELECT
  USING (auth.is_merchant_member(id));

CREATE POLICY merchant_update_policy ON merchants
  FOR UPDATE
  USING (auth.has_merchant_role(id, 'ADMIN'))
  WITH CHECK (auth.has_merchant_role(id, 'ADMIN'));

-- -----------------------------------------------------------------------------
-- 2. Products Table Policies
-- -----------------------------------------------------------------------------
CREATE POLICY products_read_policy ON products
  FOR SELECT
  USING (auth.is_merchant_member(merchant_id));

CREATE POLICY products_write_policy ON products
  FOR INSERT
  WITH CHECK (auth.has_merchant_role(merchant_id, 'MANAGER'));

CREATE POLICY products_update_policy ON products
  FOR UPDATE
  USING (auth.has_merchant_role(merchant_id, 'MANAGER'))
  WITH CHECK (auth.has_merchant_role(merchant_id, 'MANAGER'));

CREATE POLICY products_delete_policy ON products
  FOR DELETE
  USING (auth.has_merchant_role(merchant_id, 'ADMIN'));

-- -----------------------------------------------------------------------------
-- 3. Storefront Scans & Diagnoses Policies
-- -----------------------------------------------------------------------------
CREATE POLICY scans_read_policy ON storefront_scans
  FOR SELECT
  USING (auth.is_merchant_member(merchant_id));

CREATE POLICY diagnoses_read_policy ON diagnoses
  FOR SELECT
  USING (auth.is_merchant_member(merchant_id));

CREATE POLICY evidence_read_policy ON evidence_items
  FOR SELECT
  USING (auth.is_merchant_member(merchant_id));

-- -----------------------------------------------------------------------------
-- 4. Correction Proposals Policies
-- -----------------------------------------------------------------------------
CREATE POLICY proposals_read_policy ON correction_proposals
  FOR SELECT
  USING (auth.is_merchant_member(merchant_id));

CREATE POLICY proposals_update_policy ON correction_proposals
  FOR UPDATE
  USING (auth.has_merchant_role(merchant_id, 'ADMIN'))
  WITH CHECK (auth.has_merchant_role(merchant_id, 'ADMIN'));

-- -----------------------------------------------------------------------------
-- 5. Orders & Payments Policies
-- -----------------------------------------------------------------------------
CREATE POLICY orders_read_policy ON orders
  FOR SELECT
  USING (auth.is_merchant_member(merchant_id));

CREATE POLICY captures_read_policy ON payment_captures
  FOR SELECT
  USING (auth.is_merchant_member(merchant_id));

-- -----------------------------------------------------------------------------
-- 6. Audit Events Policies (Append-only for tenant, immutable)
-- -----------------------------------------------------------------------------
CREATE POLICY audit_events_read_policy ON audit_events
  FOR SELECT
  USING (auth.is_merchant_member(merchant_id));

CREATE POLICY audit_events_insert_policy ON audit_events
  FOR INSERT
  WITH CHECK (auth.is_merchant_member(merchant_id));
