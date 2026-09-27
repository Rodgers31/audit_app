"""Email service for newsletter welcome + transactional emails.

Uses SMTP credentials from settings.  Every outgoing message includes
an HMAC-signed one-click unsubscribe link (RFC 8058).
"""

import hashlib
import hmac
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate
from urllib.parse import quote

from config.settings import settings

logger = logging.getLogger(__name__)

# ── Token helpers ────────────────────────────────────────────────────


def _hmac_key() -> bytes:
    """Derive a stable HMAC key from the app SECRET_KEY."""
    return settings.SECRET_KEY.encode("utf-8")


def generate_unsubscribe_token(email: str) -> str:
    """Create an HMAC-SHA256 hex token for *email*."""
    return hmac.new(_hmac_key(), email.lower().encode(), hashlib.sha256).hexdigest()


def verify_unsubscribe_token(email: str, token: str) -> bool:
    """Constant-time verification of an unsubscribe token."""
    expected = generate_unsubscribe_token(email)
    # compare_digest(str, str) rejects non-ASCII. Malformed public input is
    # an invalid signature, not a server error.
    if not isinstance(token, str) or len(token) != 64 or not token.isascii():
        return False
    return hmac.compare_digest(expected, token)


def build_unsubscribe_url(email: str) -> str:
    """Full URL to the frontend unsubscribe page with signed token."""
    token = generate_unsubscribe_token(email)
    base = settings.FRONTEND_URL.rstrip("/")
    return f"{base}/newsletter/unsubscribe?email={quote(email)}&token={token}"


# ── HTML email template ──────────────────────────────────────────────

_WELCOME_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background-color:#F5F0E8;font-family:'Inter',Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
         style="background-color:#F5F0E8;padding:32px 16px;">
    <tr><td align="center">
      <table role="presentation" width="560" cellpadding="0" cellspacing="0"
             style="max-width:560px;width:100%;background:#1B3A2A;border-radius:24px;overflow:hidden;">
        <!-- Header -->
        <tr>
          <td style="padding:40px 32px 24px;text-align:center;">
            <div style="width:48px;height:48px;border-radius:14px;background:rgba(74,124,92,0.25);
                        display:inline-flex;align-items:center;justify-content:center;
                        border:1px solid rgba(74,124,92,0.35);margin-bottom:16px;">
              <span style="font-size:24px;">📬</span>
            </div>
            <h1 style="color:#ffffff;font-size:22px;margin:0 0 8px;font-weight:700;">
              Welcome to Kenya Public Money Tracker
            </h1>
            <p style="color:rgba(255,255,255,0.6);font-size:14px;margin:0;line-height:1.6;">
              Thank you for subscribing, <strong style="color:rgba(255,255,255,0.85);">{email}</strong>!
            </p>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="padding:0 32px 32px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                   style="background:rgba(255,255,255,0.07);border-radius:16px;border:1px solid rgba(74,124,92,0.25);">
              <tr>
                <td style="padding:24px;">
                  <p style="color:rgba(255,255,255,0.85);font-size:14px;line-height:1.7;margin:0 0 16px;">
                    You'll receive a concise weekly digest covering:
                  </p>
                  <table role="presentation" cellpadding="0" cellspacing="0" style="margin-bottom:16px;">
                    <tr><td style="padding:4px 0;color:rgba(255,255,255,0.75);font-size:14px;">
                      ✅ &nbsp;New audit reports from the Auditor General
                    </td></tr>
                    <tr><td style="padding:4px 0;color:rgba(255,255,255,0.75);font-size:14px;">
                      ✅ &nbsp;National &amp; county budget updates
                    </td></tr>
                    <tr><td style="padding:4px 0;color:rgba(255,255,255,0.75);font-size:14px;">
                      ✅ &nbsp;Debt &amp; economic indicator changes
                    </td></tr>
                    <tr><td style="padding:4px 0;color:rgba(255,255,255,0.75);font-size:14px;">
                      ✅ &nbsp;County financial transparency scorecards
                    </td></tr>
                  </table>
                  <p style="color:rgba(255,255,255,0.6);font-size:13px;line-height:1.6;margin:0;">
                    No spam, no fluff — just the data that matters for holding government accountable.
                  </p>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- CTA -->
        <tr>
          <td style="padding:0 32px 32px;text-align:center;">
            <a href="{frontend_url}"
               style="display:inline-block;padding:12px 28px;background:#4A7C5C;color:#ffffff;
                      text-decoration:none;border-radius:12px;font-size:14px;font-weight:600;">
              Explore the Dashboard →
            </a>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="padding:0 32px 32px;text-align:center;">
            <p style="color:rgba(255,255,255,0.35);font-size:11px;line-height:1.5;margin:0;">
              You're receiving this because you signed up at
              <a href="{frontend_url}" style="color:rgba(74,124,92,0.9);text-decoration:underline;">
                auditgava.com</a>.<br>
              <a href="{unsubscribe_url}"
                 style="color:rgba(201,74,74,0.9);text-decoration:underline;">
                Unsubscribe</a>
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>
"""

_WELCOME_PLAIN = """\
Welcome to Kenya Public Money Tracker!

Thank you for subscribing, {email}!

You'll receive a concise weekly digest covering:
- New audit reports from the Auditor General
- National & county budget updates
- Debt & economic indicator changes
- County financial transparency scorecards

No spam, no fluff — just the data that matters.

Explore the dashboard: {frontend_url}

---
Unsubscribe: {unsubscribe_url}
"""


# ── Sending ──────────────────────────────────────────────────────────


def _smtp_configured() -> bool:
    return bool(settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD)


def send_welcome_email(email: str) -> bool:
    """Send welcome email to a new newsletter subscriber.

    Returns True on success, False if SMTP is not configured or sending fails.
    The caller should NOT block the user flow on failure — this is best-effort.
    """
    if not _smtp_configured():
        logger.info("SMTP not configured — skipping welcome email for %s", email)
        return False

    unsubscribe_url = build_unsubscribe_url(email)
    frontend_url = settings.FRONTEND_URL.rstrip("/")

    ctx = dict(email=email, frontend_url=frontend_url, unsubscribe_url=unsubscribe_url)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Welcome to Kenya Public Money Tracker 🇰🇪"
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
    msg["To"] = email
    msg["Date"] = formatdate(localtime=True)
    # RFC 8058 one-click unsubscribe header
    msg["List-Unsubscribe"] = f"<{unsubscribe_url}>"
    msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

    msg.attach(MIMEText(_WELCOME_PLAIN.format(**ctx), "plain", "utf-8"))
    msg.attach(MIMEText(_WELCOME_HTML.format(**ctx), "html", "utf-8"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
        logger.info("Welcome email sent to %s", email)
        return True
    except Exception as exc:
        logger.error("Failed to send welcome email to %s: %s", email, exc)
        return False
