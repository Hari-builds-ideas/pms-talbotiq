"""
MFA (TOTP) helpers built on django-otp.

* enrollment creates an *unconfirmed* TOTPDevice; confirming a valid code flips
  it to confirmed and sets ``user.mfa_enabled``.
* the short-lived signed MFA token bridges the two-step login (credentials ->
  TOTP challenge) without issuing any access token until the code checks out.
"""
import base64

from django.core import signing
from django_otp.plugins.otp_totp.models import TOTPDevice

MFA_SALT = "pms.identity.mfa"
MFA_MAX_AGE_SECONDS = 300


def make_mfa_token(user):
    """A short-lived signed bearer of (user, tenant) used between the login and
    challenge steps. Signed with SECRET_KEY so it cannot be forged, and it is NOT
    a JWT access token — it grants nothing on its own."""
    return signing.dumps(
        {"uid": str(user.id), "tid": str(user.tenant_id)}, salt=MFA_SALT
    )


def read_mfa_token(token, max_age=MFA_MAX_AGE_SECONDS):
    return signing.loads(token, salt=MFA_SALT, max_age=max_age)


def rotate_unconfirmed_device(user):
    """Start (or restart) enrollment: drop any pending unconfirmed device and
    create a fresh one. Confirmed devices are left untouched."""
    TOTPDevice.objects.filter(user=user, confirmed=False).delete()
    return TOTPDevice.objects.create(user=user, name="default", confirmed=False)


def unconfirmed_device(user):
    return TOTPDevice.objects.filter(user=user, confirmed=False).order_by("-id").first()


def confirmed_device(user):
    return TOTPDevice.objects.filter(user=user, confirmed=True).order_by("-id").first()


def base32_secret(device):
    """The shared secret in base32, for manual entry into an authenticator app
    (the same secret encoded in ``device.config_url``)."""
    return base64.b32encode(device.bin_key).decode("utf-8")
