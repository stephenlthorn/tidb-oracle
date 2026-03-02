from __future__ import annotations

import json
import re
from urllib.parse import parse_qs

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import AuditStatus
from app.services.audit import write_audit_log
from app.services.chat_orchestrator import ChatOrchestrator
from app.services.slack import SlackService

router = APIRouter()


def _resolve_mode(command: str, text: str) -> tuple[str, str]:
    normalized_command = (command or "").strip().lower()
    trimmed = (text or "").strip()
    lowered = trimmed.lower()

    if normalized_command in {"/tidb-call", "/oracle-call"}:
        return "call_assistant", trimmed
    if lowered.startswith("call_assistant:"):
        return "call_assistant", trimmed.split(":", 1)[1].strip()
    if lowered.startswith("oracle:"):
        return "oracle", trimmed.split(":", 1)[1].strip()
    return "oracle", trimmed


def _format_citations(citations: list[dict], max_items: int = 3) -> list[str]:
    lines: list[str] = []
    for citation in citations[:max_items]:
        title = citation.get("title") or "Untitled source"
        source_id = citation.get("source_id") or "-"
        chunk_id = citation.get("chunk_id") or "-"
        lines.append(f"- {title} (`{source_id}` | `{chunk_id}`)")
    return lines


def _format_oracle_reply(data: dict) -> str:
    answer = (data.get("answer") or "").strip() or "I couldn't generate an answer."
    citations = _format_citations(data.get("citations") or [])
    followups = data.get("follow_up_questions") or []

    parts = [answer]
    if citations:
        parts.append("")
        parts.append("*Evidence*")
        parts.extend(citations)
    if followups:
        parts.append("")
        parts.append("*Follow-ups*")
        for idx, item in enumerate(followups[:3], start=1):
            parts.append(f"{idx}. {item}")
    return "\n".join(parts)[:3500]


def _format_call_assistant_reply(data: dict) -> str:
    sections = [
        ("What happened", data.get("what_happened") or []),
        ("Risks", data.get("risks") or []),
        ("Next steps", data.get("next_steps") or []),
        ("Questions to ask", data.get("questions_to_ask_next_call") or []),
    ]
    lines: list[str] = []
    for title, items in sections:
        if not items:
            continue
        lines.append(f"*{title}*")
        for item in items[:4]:
            lines.append(f"- {item}")
        lines.append("")
    citations = _format_citations(data.get("citations") or [])
    if citations:
        lines.append("*Evidence*")
        lines.extend(citations)
    text = "\n".join(lines).strip()
    return (text or "No call assistant output available.")[:3500]


def _format_reply(mode: str, data: dict) -> str:
    if mode == "call_assistant":
        return _format_call_assistant_reply(data)
    return _format_oracle_reply(data)


def _parse_slack_form(body: bytes) -> dict[str, str]:
    parsed = parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)
    return {k: values[-1] if values else "" for k, values in parsed.items()}


@router.post("/command")
async def slack_command(request: Request) -> dict:
    body = await request.body()
    slack = SlackService()
    try:
        slack.verify_signature(request.headers, body)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    payload = _parse_slack_form(body)
    command = payload.get("command", "")
    mode, message = _resolve_mode(command, payload.get("text", ""))
    if not message:
        return {
            "response_type": "ephemeral",
            "text": "Usage: `/tidb-oracle your question` or `call_assistant: summarize risks for call_12345`.",
        }

    user_email = await slack.resolve_user_email(payload.get("user_id"), payload.get("user_name"))
    db: Session = SessionLocal()
    orchestrator = ChatOrchestrator(db)
    input_payload = {
        "mode": mode,
        "source": "slack_command",
        "command": command,
        "user_id": payload.get("user_id"),
        "user_name": payload.get("user_name"),
        "channel_id": payload.get("channel_id"),
        "message": message,
    }

    try:
        data, retrieval = orchestrator.run(
            mode=mode,
            user=user_email,
            message=message,
            top_k=8,
            filters={},
            context={},
        )
        write_audit_log(
            db,
            actor=user_email,
            action="chat_slack_command",
            input_payload=input_payload,
            retrieval_payload=retrieval,
            output_payload=data,
            status=AuditStatus.OK,
        )
        return {"response_type": "ephemeral", "text": _format_reply(mode, data)}
    except Exception as exc:
        db.rollback()
        write_audit_log(
            db,
            actor=user_email,
            action="chat_slack_command",
            input_payload=input_payload,
            retrieval_payload={},
            output_payload={},
            status=AuditStatus.ERROR,
            error_message=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="TiDB Oracle Slack command failed.",
        ) from exc
    finally:
        db.close()


@router.post("/events")
async def slack_events(request: Request, background_tasks: BackgroundTasks) -> dict:
    body = await request.body()
    slack = SlackService()

    try:
        slack.verify_signature(request.headers, body)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON body.") from exc

    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}

    if payload.get("type") != "event_callback":
        return {"ok": True}

    event = payload.get("event") or {}
    if event.get("type") != "app_mention":
        return {"ok": True}
    if event.get("bot_id") or event.get("subtype") == "bot_message":
        return {"ok": True}

    channel = str(event.get("channel") or "").strip()
    if not channel:
        return {"ok": True}

    mention_text = re.sub(r"<@[^>]+>", "", str(event.get("text") or "")).strip()
    mode, message = _resolve_mode("", mention_text)
    if not message:
        return {"ok": True}

    background_tasks.add_task(
        _handle_slack_event,
        {
            "mode": mode,
            "event_id": payload.get("event_id"),
            "channel": channel,
            "thread_ts": str(event.get("thread_ts") or event.get("ts") or ""),
            "message": message,
            "user_id": str(event.get("user") or ""),
        },
    )
    return {"ok": True}


async def _handle_slack_event(event_input: dict) -> None:
    slack = SlackService()
    user_email = await slack.resolve_user_email(event_input.get("user_id"), None)
    db: Session = SessionLocal()
    orchestrator = ChatOrchestrator(db)
    input_payload = {
        "mode": event_input.get("mode"),
        "source": "slack_event",
        "event_id": event_input.get("event_id"),
        "channel": event_input.get("channel"),
        "thread_ts": event_input.get("thread_ts"),
        "message": event_input.get("message"),
    }

    try:
        data, retrieval = orchestrator.run(
            mode=event_input.get("mode") or "oracle",
            user=user_email,
            message=event_input.get("message") or "",
            top_k=8,
            filters={},
            context={},
        )
        await slack.post_message(
            channel=event_input.get("channel") or "",
            text=_format_reply(event_input.get("mode") or "oracle", data),
            thread_ts=event_input.get("thread_ts"),
        )
        write_audit_log(
            db,
            actor=user_email,
            action="chat_slack_event",
            input_payload=input_payload,
            retrieval_payload=retrieval,
            output_payload=data,
            status=AuditStatus.OK,
        )
    except Exception as exc:
        db.rollback()
        write_audit_log(
            db,
            actor=user_email,
            action="chat_slack_event",
            input_payload=input_payload,
            retrieval_payload={},
            output_payload={},
            status=AuditStatus.ERROR,
            error_message=str(exc),
        )
    finally:
        db.close()
