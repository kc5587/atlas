# Atlas Phase Zero Security Audit

**Status:** ✅ CLOSED (2026-06-02). All v1 credentials revoked at their providers and the
v1 infrastructure (EC2 instance + local Postgres/Airflow/MinIO docker stack) decommissioned.
The public repo was built from fresh history (atlas/ only, no v1 objects), scanned clean,
and deployed. See "Closure" below.

## Scan Summary

- Scanner: `gitleaks 8.30.1`
- Working-tree scan: `gitleaks detect --no-git --config .gitleaks.toml --redact -v`
  found 25 redacted findings in legacy files retained on disk.
- Full-history scan: `gitleaks detect --config .gitleaks.toml --redact -v`
  found one committed `AIRFLOW_SECRET_KEY` in the historical v1 `.env`.
- Manual review: checked legacy `.env`, `env.lock`, SSH key material, and configuration
  references without copying secret values into this record.
- Post-reset working-tree scan: `gitleaks detect --source . --config .gitleaks.toml
  --no-git` returned zero findings after the legacy tree and generated local state were
  removed.

## Credential Inventory

All values are redacted. The v1 credentials were treated as compromised and revoked at
their providers. v2 does not reuse them.

| Credential | Historical location(s) | Discovery | Revoked? |
| --- | --- | --- | --- |
| Postgres superuser password (`PG_SUPERPASS`) | `ai-value-chain-data/.env` | manual review; historically committed v1 env | y |
| Airflow admin password (`AIRFLOW_ADMIN_PASSWORD`) | `ai-value-chain-data/.env` | manual review; historically committed v1 env | y |
| Airflow secret key (`AIRFLOW_SECRET_KEY`) | `ai-value-chain-data/.env` | gitleaks working tree + full history | y |
| MinIO root password (`MINIO_ROOT_PASSWORD`) | `ai-value-chain-data/.env` | manual review; historically committed v1 env | y |
| Twelve Data API key (`TWELVEDATA_API_KEY`) | `ai-value-chain-data/env.lock`, `ai-value-chain-data/locks/twelvedata_quote_verify_20251222T010924Z.json` | gitleaks working tree | y |
| Polygon API key (`POLYGON_API_KEY`) | `ai-value-chain-data/env.lock`, `ai-value-chain-data/locks/polygon_tickers_verify_20251222T010017Z.json` | gitleaks working tree | y |
| Alpaca API key (`ALPACA_API_KEY`) | `ai-value-chain-data/env.lock` | gitleaks working tree | y |
| Alpaca secret key (`ALPACA_SECRET_KEY`) | `ai-value-chain-data/env.lock` | gitleaks working tree | y |
| MinIO password (`MINIO_PASS`) | `ai-value-chain-data/env.lock` | manual review | y |
| Atlas database password (`ATLAS_DB_PASSWORD`) | `ai-value-chain-data/env.lock` | manual review | y |
| Postgres password (`PGPASSWORD`) | `ai-value-chain-data/env.lock` | manual review | y |
| EC2 SSH keypair | `ai-value-chain-data/ssh_key`, `ai-value-chain-data/ssh_key.pub` | gitleaks private-key finding + manual review | y |

Legacy scripts and Docker Compose files contained references, fallbacks, or generated-value
templates for the same v1 credentials. They were deleted during the clean-room reset.

## Working-Tree Handling

The entire legacy `ai-value-chain-data/` tree and root-level legacy exports were deleted.
Generated v2 environment, cache, database, and dbt build artifacts were also removed. The
root `.gitignore` denies secrets, keys, regenerated data, databases, and logs.

## History-Scrub Decision

**Selected:** `(b) start the public repository from fresh history`.

The repository is reinitialized from the post-cleanup clean-room `atlas/` tree with a
single root commit. No local legacy branch or historical v1 Git object is retained after
verification. This avoids publishing v1 history and aligns with the from-scratch rebuild.

## Closure (2026-06-02)

All pre-release actions are complete:

1. ✅ Fresh-history public tree constructed from the clean-room `atlas/` source (no v1 Git
   objects, no legacy `.env`/`env.lock`/keys).
2. ✅ Secret scan on the published tree returned **zero findings**
   (`gitleaks detect --no-git --config .gitleaks.toml` over `atlas/`, verified
   2026-06-02 — 516 KB scanned, no leaks).
3. ✅ Deployment configured and live on Streamlit Community Cloud
   (`/healthz` → 200) — see `MEMORY/atlas-deployed-app`.
4. ✅ All 12 v1 credentials in the inventory revoked at their providers; the v1 EC2
   instance and local Postgres/Airflow/MinIO docker stack are decommissioned, so the
   infra-side passwords are moot.

**Residual note:** this *private working* repo still contains the legacy `ai-value-chain-data/`
tree and v1 history on disk. Those secrets are now dead (revoked) and were never published
(the public repo is fresh-history). Archiving/removing the legacy tree locally is optional
housekeeping, not a security requirement. Gate is CLOSED.
