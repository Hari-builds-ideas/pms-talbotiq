# Environment reference — variables added or changed by this build

The full pre-existing list is documented in `.env.example` and audited in
`docs/AUDIT/REPO_FACTS.md` §9.1. This file covers only what this build introduced
or changed, so a deployer can see the delta without re-reading everything.

Secrets are env-only. No value in this file, in the repo, or in any log.

---

## New

| Name | Required? | Default | What it does |
|---|---|---|---|
| `FIELD_ENCRYPTION_KEY` | Optional, but required to use per-tenant AI keys | `""` | Fernet key(s) encrypting secrets that must be read back — today a tenant's own LLM API key. Comma-separated for rotation: the **first** key encrypts, **all** are tried for decryption. |

### `FIELD_ENCRYPTION_KEY` in detail

Generate:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**Unset is a safe state, not a broken one.** The Admin Hub's "set AI key" action
refuses with an explanation, and every tenant falls back to the deployment-wide
provider key. What it will *never* do is store a provider credential in plaintext
because the variable was missing — that write is refused instead.

**Rotation** (no window where existing ciphertext is unreadable):

1. Prepend the new key: `FIELD_ENCRYPTION_KEY=<new>,<old>`
2. Deploy. New writes use `<new>`; old rows still decrypt with `<old>`.
3. Re-save the affected rows (an admin re-entering their key, or a management
   command) so everything is under `<new>`.
4. Drop `<old>`: `FIELD_ENCRYPTION_KEY=<new>`

**If the key is lost**, stored tenant keys become undecryptable. That is not an
outage: `resolve_provider` treats an unreadable key as "no tenant key" and falls
back to the environment key. Admins re-enter their keys.

---

## Changed behaviour of existing variables

| Name | Change |
|---|---|
| `LLM_PROVIDER` | Now the **deployment-wide fallback** rather than the only source. Resolution is tenant key → `LLM_PROVIDER` + its env key → not configured. |
| `GEMINI_API_KEY` / `OPENAI_API_KEY` / `GROQ_API_KEY` / `LLM_API_KEY` | Unchanged in meaning, but now only consulted when the tenant has not set its own key. |

---

## Still needed from a human before go-live

Recorded here so the list is in one place; see `docs/BUILD/OVERNIGHT_SUMMARY.md`
for the full deploy sequence.

| Name | Why it is not set | Blocking? |
|---|---|---|
| `FIELD_ENCRYPTION_KEY` | Must be generated per environment; generating one here and committing it would defeat the purpose | No — per-tenant keys are simply unavailable until set |
| `GEMINI_API_KEY` | The enterprise key is added later by an admin (FACTS) | No — AI degrades to an honest "not configured" state |
| `DOMAIN`, `ACME_EMAIL` | No domain yet; the stack runs on a bare IP (FACTS) | No — TLS is a one-variable change later, see `ENABLE_TLS.md` |
| SMTP (`EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_BACKEND`) | No provider chosen yet (FACTS) | No — the console backend stays active |
