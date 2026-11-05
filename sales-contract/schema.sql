CREATE TABLE IF NOT EXISTS offers (
  id TEXT PRIMARY KEY,
  token_hash TEXT NOT NULL UNIQUE,
  quote_number TEXT NOT NULL UNIQUE,
  buyer_company TEXT NOT NULL,
  signer_name TEXT NOT NULL,
  signer_email TEXT NOT NULL,
  service_details TEXT NOT NULL,
  agreement_text TEXT NOT NULL,
  agreement_hash TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'quoted',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  signed_at TIMESTAMPTZ,
  signed_by TEXT,
  signed_email TEXT,
  signed_ip TEXT,
  signed_user_agent TEXT,
  signature_image TEXT,
  stripe_checkout_session_id TEXT,
  stripe_subscription_id TEXT,
  stripe_customer_id TEXT,
  stripe_invoice_url TEXT,
  stripe_receipt_url TEXT,
  paid_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS webhook_events (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_offers_subscription ON offers (stripe_subscription_id);
CREATE INDEX IF NOT EXISTS idx_offers_customer ON offers (stripe_customer_id);
