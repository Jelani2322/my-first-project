"""Send alerts to the console, your phone (ntfy.sh / Telegram) and/or email."""
import smtplib
from email.message import EmailMessage

import requests


class Notifier:
    def __init__(self, cfg):
        self.n = cfg["notify"]

    def send(self, title, body, urgent=False):
        n, sent = self.n, []
        if n.get("console", True):
            bar = "=" * 70
            print(f"\n{bar}\n{'🔔 ' if urgent else ''}{title}\n{bar}\n{body}\n", flush=True)
            sent.append("console")
        if n.get("ntfy_topic"):
            self._try(sent, "ntfy", lambda: requests.post(
                f"https://ntfy.sh/{n['ntfy_topic']}", data=body.encode(),
                headers={"Title": title.encode("ascii", "ignore").decode(), "Priority": "high" if urgent else "default"},
                timeout=10).raise_for_status())
        if n.get("telegram_bot_token") and n.get("telegram_chat_id"):
            self._try(sent, "telegram", lambda: requests.post(
                f"https://api.telegram.org/bot{n['telegram_bot_token']}/sendMessage",
                json={"chat_id": n["telegram_chat_id"], "text": f"{title}\n\n{body}"}, timeout=10).raise_for_status())
        if n.get("email_smtp_host") and n.get("email_to"):
            self._try(sent, "email", lambda: self._email(title, body))
        return sent

    def _email(self, title, body):
        n = self.n
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = title, n["email_user"], n["email_to"]
        msg.set_content(body)
        with smtplib.SMTP(n["email_smtp_host"], int(n["email_smtp_port"]), timeout=15) as s:
            s.starttls()
            s.login(n["email_user"], n["email_password"])
            s.send_message(msg)

    @staticmethod
    def _try(sent, name, fn):
        try:
            fn()
            sent.append(name)
        except Exception as e:  # never let a failed alert kill the monitor loop
            print(f"[warn] {name} notification failed: {e}")
