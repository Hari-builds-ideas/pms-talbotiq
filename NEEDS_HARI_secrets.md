# NEEDS_HARI — production secrets storage for integrations

**Status:** non-blocking. A safe default was chosen and the build proceeded.

## The question
Module 12 (Jira + Slack integrations) needs per-tenant credentials (a Jira API
token, a Slack webhook URL/token). Where should those secrets live in production?

## The safe default I chose (and built on tonight)
Secrets are **NEVER stored in a plaintext DB column.** The `TenantIntegration`
model stores only:
- non-secret `config` (JSON: base_url, project, channel name, value field, …), and
- a **`secret_ref`** — the *NAME of an environment variable* that holds the actual
  token (e.g. `JIRA_TOKEN_ACME`, `SLACK_WEBHOOK_ACME`), never the token itself.

`apps/integrations/secrets.py::resolve_secret(integration)` reads
`os.environ[secret_ref]` (falling back to the convention
`<KIND>_TOKEN_<TENANT_SLUG_UPPER>`). The value is **never logged** and never
serialized out of any endpoint. A tenant whose env var is unset resolves to `None`,
so the integration is a clean no-op (no crash, no fabricated send/fetch). **No real
Jira/Slack credentials are used anywhere tonight** — production stays on the
NotConfigured/no-op path until a key is provided; tests use in-repo fakes.

## What Hari needs to decide for production
The env-var convention is fine for a single VM / docker-compose, but for a real
multi-tenant deployment please choose a **proper secrets store** and point
`resolve_secret` at it (it is a single function to swap):
- **Recommended:** a managed secrets manager — AWS Secrets Manager / GCP Secret
  Manager / HashiCorp Vault — keyed per tenant + integration kind, fetched at use
  time with a short in-process cache. (Avoids putting tokens in the process
  environment, supports rotation + audit.)
- **Acceptable interim:** Django-encrypted field (Fernet) with the key in the
  secrets manager — keeps tokens out of plaintext but still in the DB.
- **Not acceptable for prod:** plaintext token columns (we deliberately did not
  build this).

Also confirm the **Slack delivery mechanism** (incoming webhook per channel vs. a
bot token + `chat.postMessage`) — the client is a thin, swappable adapter
(`apps/integrations/clients.py`), so either is a small change behind the same
`secret_ref`.

Until you say otherwise, integrations use the env-var `secret_ref` convention and
stay no-op when unset.
