# Turning on HTTPS

**Today this deployment serves plain HTTP.** That is deliberate, not an
oversight: Let's Encrypt cannot issue a certificate for a bare IP address, and
there is no DNS name pointed at the VM yet. Everything else is already in place,
so switching TLS on is one variable and one restart.

Until then, be honest about what it means. Every request between a browser and
this server — the login POST, the JWT on every subsequent call, every performance
review being typed — crosses the network readable and alterable by anyone on the
path: the coffee-shop Wi-Fi, the office router, the hosting provider's network.
It is fine for a QA handover on a known network. It is not fine once real
employees write real reviews in it.

`manage.py check --deploy` prints `pms.W003` on every deploy while this is the
case, so the state stays visible rather than becoming permanent by inattention.

---

## What "one variable" means

`DOMAIN` is read by both halves of the stack:

| Reads it | Empty (today) | Set |
| --- | --- | --- |
| `Caddyfile` | site address falls back to `:80` — plain HTTP, no ACME attempted | obtains and auto-renews a Let's Encrypt certificate, redirects http → https |
| `config/settings/prod.py` | `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` off, HSTS 0 | all on, HSTS one year |

They are deliberately not two switches. Two switches is one switch somebody
flips halfway — a valid certificate with cookies still going out without
`Secure` looks completely healthy and is not.

---

## Before you start

You need:

- a hostname you control, e.g. `pms.talbotiq.com`;
- the VM's external IP: `gcloud compute instances describe pms-prod --zone asia-south1-a --format='get(networkInterfaces[0].accessConfigs[0].natIP)'`;
- ports 80 **and** 443 open to the internet on the VM. Both — the HTTP-01
  challenge is answered on :80, so closing it after issuance breaks renewal about
  60 days later, not on the day you close it:

  ```bash
  gcloud compute firewall-rules create allow-http-https \
    --allow tcp:80,tcp:443 --target-tags=pms-prod --direction=INGRESS
  ```

Roughly 15 minutes, most of it DNS propagation.

---

## Step 1 — Point DNS at the VM

Create an **A record** for the hostname pointing at the VM's external IP. In
Cloud DNS:

```bash
gcloud dns record-sets create pms.talbotiq.com. \
  --zone=<your-zone> --type=A --ttl=300 --rrdatas=<VM_EXTERNAL_IP>
```

Give the VM a **static** IP first if it does not have one
(`gcloud compute addresses create ...`, then attach it). An ephemeral IP changes
on stop/start, which breaks DNS and renewal at the same time.

**Wait for it to resolve before going further.** This is the step people skip,
and it is the step that costs you a rate-limit window:

```bash
dig +short pms.talbotiq.com    # must print the VM's IP
```

If that is empty or wrong, stop here. Caddy will ask Let's Encrypt for a
certificate, the HTTP-01 challenge will fail, and **Let's Encrypt allows only 5
failures per account per hostname per hour**. Burn the window and you wait,
whatever you fix in the meantime.

## Step 2 — Set the variables

On the VM, in `/srv/pms/.env` (or wherever the compose env comes from):

```bash
DOMAIN=pms.talbotiq.com
ACME_EMAIL=ops@talbotiq.com

# these three must change with it
PUBLIC_APP_URL=https://pms.talbotiq.com
DJANGO_ALLOWED_HOSTS=pms.talbotiq.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://pms.talbotiq.com
```

Why each of the last three:

- **`PUBLIC_APP_URL`** builds every password-reset and invitation link. Left on
  the IP, those links keep working *and* keep sending single-use tokens over
  plain HTTP. `check --deploy` warns if it still starts with `http://` once
  `DOMAIN` is set.
- **`DJANGO_ALLOWED_HOSTS`** — Django rejects the new hostname with a 400 until
  it is listed. Keep the IP in the list only if you still need it; each entry is
  a host that may serve the app.
- **`DJANGO_CSRF_TRUSTED_ORIGINS`** — needs the **`https://` scheme included**.
  Without it every session-authenticated POST (the Django admin, the allauth SSO
  flow) fails CSRF validation, and the error message will not mention this
  setting.

`DJANGO_SECURE_SSL_REDIRECT`, `DJANGO_SESSION_COOKIE_SECURE`,
`DJANGO_CSRF_COOKIE_SECURE` and `DJANGO_HSTS_SECONDS` should stay **empty**.
Empty means "follow `DOMAIN`", which is right in both modes. They exist for the
one topology that needs them — TLS terminated at a load balancer that forwards
plain HTTP — and setting them by hand is how you end up with a certificate and
insecure cookies.

## Step 3 — Restart the edge and the app

```bash
cd /srv/pms
docker compose -f docker-compose.prod.yml up -d caddy web worker beat
```

Caddy requests the certificate on startup. Watch it happen:

```bash
docker compose -f docker-compose.prod.yml logs -f caddy
```

Success looks like `certificate obtained successfully` followed by
`serving initial configuration`. It normally takes 10–30 seconds.

## Step 4 — Verify, in this order

```bash
# 1. the certificate is real and for the right name
curl -sSI https://pms.talbotiq.com/healthz | head -1        # HTTP/2 200

# 2. http is redirected, not merely also-served
curl -sSI http://pms.talbotiq.com/ | head -3                # 308 -> https://

# 3. HSTS is present on the TLS response
curl -sSI https://pms.talbotiq.com/ | grep -i strict-transport

# 4. the cookies carry Secure
curl -sSI https://pms.talbotiq.com/api/auth/csrf | grep -i set-cookie

# 5. Django agrees it is deployed properly — pms.W003 must be GONE
docker compose -f docker-compose.prod.yml run --rm web python manage.py check --deploy
```

Then log in through the browser once, and send yourself a password reset. The
link in the email must start with `https://`. That single click exercises
`PUBLIC_APP_URL`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` and the cookie flags
at once — it is the fastest way to find the one you missed.

---

## If it goes wrong

**Certificate never arrives.** Check DNS actually resolves to this VM
(`dig +short`), then that :80 reaches it from outside (`curl -I http://<IP>/`
from your laptop, not from the VM). Cloud firewall rules and the VM's own
`iptables` are two different things; check both. Read the Caddy log — it names
the failed challenge.

**Rate-limited** (`too many failed authorizations`). Stop restarting Caddy; each
attempt costs another. Fix DNS and reachability first, confirm from outside the
network, and only then restart. To iterate without burning attempts, point Caddy
at the staging CA — add `acme_ca https://acme-staging-v02.api.letsencrypt.org/directory`
to the global block in the `Caddyfile`. Staging certificates are untrusted by
browsers, which is exactly what you want while testing the plumbing. **Remove
that line before going live.**

**Redirect loop.** Django is not seeing `X-Forwarded-Proto`. The `Caddyfile`
sets it and `prod.py` trusts it via `SECURE_PROXY_SSL_HEADER`; if you have put
something else in front of Caddy, that thing must forward the header too — and
`DJANGO_NUM_PROXIES` becomes 2 (see `pms.W002`).

**CSRF failures on the admin or SSO after the switch.** `DJANGO_CSRF_TRUSTED_ORIGINS`
is missing the `https://` scheme, or still lists only the IP.

**Everything 400s.** The new hostname is not in `DJANGO_ALLOWED_HOSTS`.

---

## Rolling back

Clear `DOMAIN` and restart. The stack returns to HTTP on the IP.

One caveat, and it is the reason to get DNS right before step 2 rather than
after: once a browser has seen the HSTS header it will refuse plain HTTP to that
hostname for a year, ignoring the rollback entirely. That only binds the
hostname, never the IP — so the rollback still works, and anyone who already
visited the HTTPS site must use the IP until you put TLS back. Clearing it
locally is `chrome://net-internals/#hsts`.

---

## After it is on

- **Keep the `caddy_data` volume.** It holds the issued certificate and the ACME
  account key. Destroying it forces re-issue, and Let's Encrypt permits 5
  duplicate certificates per week — lose it twice in a week and the site is
  HTTP-only until the window rolls.
- **Renewal is automatic** at ~30 days remaining and needs no action, provided
  :80 stays open and DNS keeps pointing here.
- **Set `ACME_EMAIL`** if you have not. It is the only warning you get before a
  failed renewal becomes an outage 60 days later.
- Re-run `check --deploy` and confirm `pms.W003` is gone. If it still appears,
  the containers are running with the old environment — recreate them rather
  than restarting.
