from __future__ import annotations

import smtplib
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.models import MessageChannel, MessageMode, OutboundMessage
from app.utils.email_utils import blocked_recipients
from app.utils.hashing import sha256_json


class MessagingService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def validate_recipients(self, to: list[str], cc: list[str]) -> tuple[bool, str | None]:
        bad = blocked_recipients([*to, *cc], self.settings.domain_allowlist)
        if bad:
            return False, "Outbound messages are restricted to internal recipients (@pingcap.com)."
        return True, None

    def build_email_subject(self, account: str | None) -> str:
        base = account or "Account"
        return f"{base} call takeaways + next-step questions"

    def build_email_body(
        self,
        *,
        account: str | None,
        summary: str,
        next_steps: list[str],
        questions: list[str],
        collateral: list[dict],
        sources: list[str],
    ) -> str:
        lines = ["Hi team,", "", "Key takeaways from the call:", f"- {summary}", "", "Recommended next steps:"]
        for i, step in enumerate(next_steps, start=1):
            lines.append(f"{i}) {step}")

        lines.extend(["", "Questions to ask next call:"])
        for q in questions:
            lines.append(f"- {q}")

        lines.extend(["", "Suggested collateral (internal):"])
        for item in collateral:
            title = item.get("title", "Untitled")
            reason = item.get("reason", "")
            lines.append(f"- {title}: {reason}")

        lines.extend(["", "Sources:"])
        for src in sources:
            lines.append(f"- {src}")
        lines.append("")
        lines.append("-TiDB Oracle")
        return "\n".join(lines)

    def _send_email(self, *, to: list[str], cc: list[str], subject: str, body: str) -> None:
        if not self.settings.smtp_host:
            raise RuntimeError("SMTP host is not configured")

        msg = EmailMessage()
        msg["From"] = self.settings.smtp_from
        msg["To"] = ", ".join(to)
        if cc:
            msg["Cc"] = ", ".join(cc)
        msg["Subject"] = subject
        msg.set_content(body)

        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port) as server:
            if self.settings.smtp_username and self.settings.smtp_password:
                server.starttls()
                server.login(self.settings.smtp_username, self.settings.smtp_password)
            server.send_message(msg)

    def draft_or_send(
        self,
        *,
        to: list[str],
        cc: list[str],
        subject: str,
        body: str,
        requested_mode: str,
        chorus_call_id: str | None,
        artifact_id,
    ) -> OutboundMessage:
        ok, reason = self.validate_recipients(to, cc)
        mode = MessageMode.DRAFT

        if not ok:
            mode = MessageMode.BLOCKED
        else:
            wants_send = requested_mode == "send" and self.settings.email_mode == "send"
            if wants_send:
                self._send_email(to=to, cc=cc, subject=subject, body=body)
                mode = MessageMode.SENT
            else:
                mode = MessageMode.DRAFT

        row = OutboundMessage(
            mode=mode,
            channel=MessageChannel.EMAIL,
            to_recipients=to,
            cc_recipients=cc,
            subject=subject,
            body=body,
            reason_blocked=reason,
            chorus_call_id=chorus_call_id,
            artifact_id=artifact_id,
            content_hash=sha256_json({"to": to, "cc": cc, "subject": subject, "body": body}),
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row
