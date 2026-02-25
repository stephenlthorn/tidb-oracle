from __future__ import annotations


def is_internal_email(email: str, allowlist: list[str]) -> bool:
    if "@" not in email:
        return False
    domain = email.rsplit("@", 1)[1].lower().strip()
    return domain in {d.lower() for d in allowlist}


def blocked_recipients(recipients: list[str], allowlist: list[str]) -> list[str]:
    return [email for email in recipients if not is_internal_email(email, allowlist)]
