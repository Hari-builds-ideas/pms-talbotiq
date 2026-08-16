# Email

**No SMTP provider is configured yet.** The console backend is active, so every
message this product sends is written to the container log and delivered to
nobody. Everything else is built: templates, the sender, the four flows, the
verification command. Going live is **environment variables only** — there is no
code change waiting to be made.

While this is the case, `manage.py check --deploy` fails with `pms.E001`. That is
deliberate: on the console backend nobody can reset a password, accept an
invitation or recover an account, and every one of those requests returns 200
with no error anywhere.

---

## Turning it on

### 1. Pick a provider and get credentials

Any SMTP relay works. Three common ones, with the exact values:

**SendGrid**

```bash
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.sendgrid.net
EMAIL_PORT=587
EMAIL_HOST_USER=apikey          # the literal word "apikey"
EMAIL_HOST_PASSWORD=<the API key>
EMAIL_USE_TLS=true
```

**Amazon SES** (use the SMTP credentials, which are *not* your AWS access key)

```bash
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=email-smtp.ap-south-1.amazonaws.com   # the region you verified
EMAIL_PORT=587
EMAIL_HOST_USER=<SES SMTP username>
EMAIL_HOST_PASSWORD=<SES SMTP password>
EMAIL_USE_TLS=true
```

A new SES account is **sandboxed**: it can only send to addresses you have
verified. Request production access before go-live, or every invitation to a
real customer silently bounces.

**Google Workspace / Gmail**

```bash
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=no-reply@your-domain.com
EMAIL_HOST_PASSWORD=<an App Password, not the account password>
EMAIL_USE_TLS=true
```

Workspace applies a daily send cap (commonly 2,000). Fine for a pilot, not for a
tenant bulk-importing 500 employees on their first day.

### 2. Set the rest

```bash
DEFAULT_FROM_EMAIL="Axiom <no-reply@your-domain.com>"
EMAIL_REPLY_TO=support@your-domain.com
PUBLIC_APP_URL=https://pms.your-domain.com
```

`PUBLIC_APP_URL` is the one to get right. **Every link in every email is built
from it**, and it is the setting that breaks silently: wrong, the mail still
sends, the endpoint still returns 200, the log still says sent — and the
recipient gets a link to somebody's laptop. The only signal is a user reporting
"the link doesn't work", days later.

`DEFAULT_FROM_EMAIL` must be on a domain you control and have authorised at the
provider. A From address on an unrelated domain is usually accepted by the relay
and then filtered into spam on arrival, which looks identical to success from
this side.

### 3. Verify from the deployment

```bash
docker compose -f docker-compose.prod.yml run --rm web \
  python manage.py send_test_email you@your-domain.com
```

It prints the resolved configuration (never the password), refuses to run on a
non-delivering backend, sends a real multipart message, and tells you what the
provider said. Then:

```bash
docker compose -f docker-compose.prod.yml run --rm web \
  python manage.py check --deploy   # pms.E001 must be gone
```

Finally, exercise a real flow — request a password reset for your own account
and click the link in the email. That single click tests `PUBLIC_APP_URL`,
`ALLOWED_HOSTS`, the cookie flags and the token in one go.

---

## Every variable

| Variable | Default | What it does |
| --- | --- | --- |
| `EMAIL_BACKEND` | console | `django.core.mail.backends.smtp.EmailBackend` to actually send |
| `EMAIL_HOST` | *(empty)* | SMTP hostname |
| `EMAIL_PORT` | `587` | 587 with STARTTLS, or 465 with implicit TLS |
| `EMAIL_HOST_USER` | *(empty)* | SMTP username |
| `EMAIL_HOST_PASSWORD` | *(empty)* | SMTP password or API key |
| `EMAIL_USE_TLS` | `true` | STARTTLS on 587 |
| `EMAIL_USE_SSL` | `false` | Implicit TLS on 465. **Never both** — Django refuses |
| `EMAIL_TIMEOUT` | `10` | Seconds. Django's own default is *wait forever*, which lets a stalled provider pin a gunicorn worker until the app stops responding |
| `DEFAULT_FROM_EMAIL` | `Axiom <no-reply@localhost>` | The From address |
| `EMAIL_REPLY_TO` | `SUPPORT_EMAIL` | Where a reply goes; unset means replies vanish |
| `PUBLIC_APP_URL` | *(required in prod)* | The hostname every link is built from |
| `APP_NAME` | `Axiom` | Product name in subjects and bodies |
| `SUPPORT_EMAIL` | *(empty)* | Printed in the footer when set; omitted when not |

---

## What gets sent

Four messages, each with a plaintext and an HTML part
(`templates/emails/<name>.{txt,html}`):

| Template | Trigger | Goes to |
| --- | --- | --- |
| `password_reset` | `POST /api/auth/password-reset` | the account holder |
| `invitation` | `POST /api/admin/invitations` | the invitee |
| `email_change` | `POST /api/auth/email-change` | the **new** address |
| `welcome` | `POST /api/auth/signup` | the new workspace admin |

Plus `test`, sent only by `send_test_email`.

This product sends **no marketing and no notification email** — nothing anyone
would want to unsubscribe from. Every message is transactional and follows an
action the recipient took, which is why there is no unsubscribe footer.

### Editing a template

Both halves, always. `send_templated_email` renders `.txt` and `.html` and fails
the send if either is missing — a message with only one part arrives either
looking like a phishing attempt (plaintext alone) or as nothing at all (HTML
alone, to a plaintext reader).

The HTML is deliberately plain: tables, inline styles, no external assets. Email
clients are not browsers — Outlook renders through Word, and a flexbox layout
arrives as a stack of unstyled text. No images at all, since remote images are
blocked by default in most clients and a tracking pixel in a password-reset email
is not something this product should be doing.

**The plaintext half is rendered with autoescaping OFF**, in the sender, not per
template. Reset URLs carry query parameters, so with escaping on `&` becomes
`&amp;` and the link a recipient copies out of the text arrives with a parameter
named `amp;uid`. The reset then fails with an invalid-token error that points at
the token rather than at the escaping. There is a test pinning this.

---

## When mail does not arrive

Sending is **best-effort everywhere by design**: a password-reset endpoint that
500s on an SMTP outage tells the caller their account exists, and an invitation
that 500s after the row was written leaves an invite that cannot be resent. So a
failure is logged, not raised — which means a misconfiguration is quiet, and the
log is where you look.

```bash
docker compose -f docker-compose.prod.yml logs web | grep pms.mail
```

| Symptom | Usual cause |
| --- | --- |
| `authentication failed` | For SendGrid the username is the literal `apikey`; for SES the SMTP credentials are not the AWS access key |
| Connection times out | Port 587 blocked outbound. GCP does not block 587, but a VPC firewall rule can |
| Accepted, never arrives | SPF/DKIM missing for the From domain, or an SES account still in sandbox |
| Arrives, link is dead | `PUBLIC_APP_URL` is wrong |
| `EMAIL_USE_TLS and EMAIL_USE_SSL are both on` | They are different things — STARTTLS on 587 versus implicit TLS on 465. Turn off whichever does not match the provider |
