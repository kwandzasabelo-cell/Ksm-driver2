# services/notifications.py — Alert dispatcher (email + WhatsApp via Twilio)
# All credentials come from environment variables via core.secrets.
# If no credentials are set, alerts are logged to console only (safe default).
from __future__ import annotations
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def _send_email(subject: str, body: str) -> bool:
    from core.secrets import smtp_host, smtp_port, smtp_user, smtp_password, alert_email_to
    host = smtp_host()
    if not host:
        return False
    try:
        import smtplib
        from email.mime.text import MIMEText
        msg           = MIMEText(body, "plain")
        msg["Subject"] = f"[KSM Fleet] {subject}"
        msg["From"]    = smtp_user()
        msg["To"]      = alert_email_to()
        with smtplib.SMTP(host, smtp_port()) as s:
            s.starttls()
            s.login(smtp_user(), smtp_password())
            s.send_message(msg)
        logger.info("Alert email sent: %s", subject)
        return True
    except Exception as e:
        logger.warning("Email alert failed: %s", e)
        return False


def _send_whatsapp(message: str) -> bool:
    from core.secrets import twilio_sid, twilio_token, twilio_from, alert_phone_to
    sid = twilio_sid()
    if not sid:
        return False
    try:
        from twilio.rest import Client
        client = Client(sid, twilio_token())
        client.messages.create(
            body=message,
            from_=twilio_from(),
            to=alert_phone_to(),
        )
        logger.info("WhatsApp alert sent.")
        return True
    except Exception as e:
        logger.warning("WhatsApp alert failed: %s", e)
        return False


def send_alert(subject: str, body: str, channel: str = "all") -> dict:
    """
    Send an alert through configured channels.
    channel: 'email' | 'whatsapp' | 'all'
    Returns dict with results per channel.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_body = f"{body}\n\n---\nKSM Smart Freight Solutions\n{now}"
    results = {}
    if channel in ("email", "all"):
        results["email"] = _send_email(subject, full_body)
    if channel in ("whatsapp", "all"):
        results["whatsapp"] = _send_whatsapp(f"[KSM Alert] {subject}\n{body}")
    if not any(results.values()):
        logger.info("ALERT (no channel configured): %s — %s", subject, body)
    return results


# ── Convenience alert types ───────────────────────────────────────────────────

def alert_service_overdue(truck_reg: str, km_overdue: float) -> None:
    send_alert(
        f"SERVICE OVERDUE — {truck_reg}",
        f"Truck {truck_reg} is {km_overdue:,.0f} km overdue for service.\n"
        f"Please schedule maintenance immediately."
    )


def alert_high_risk_trip(truck_reg: str, route: str, risk_score: float) -> None:
    send_alert(
        f"HIGH RISK TRIP — {truck_reg}",
        f"Trip logged for {truck_reg} on route {route} "
        f"with risk score {risk_score:.0f}/100.\n"
        f"Review driver behaviour and route conditions."
    )


def alert_driver_login(driver_id: str, truck_reg: str) -> None:
    send_alert(
        f"Driver Login — {driver_id}",
        f"Driver {driver_id} logged in and is assigned to truck {truck_reg}.",
        channel="email",  # Login alerts email only — not WhatsApp (too noisy)
    )
