from typing import Any, Dict

import httpx

from .. import db
from ..config import get_settings


TELEGRAM_MAX_MESSAGE_LENGTH = 3900
TELEGRAM_SEND_TIMEOUT_SECONDS = 8


class NotificationError(RuntimeError):
    pass


def send_notification(target: str, title: str, body: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    settings = get_settings()
    mode = settings.notification_mode.strip().lower()
    if mode == "telegram":
        return _send_telegram_notification(target, title, body, payload)
    return _record_notification("dry-run", target, title, body, payload, "recorded", None)


def send_test_notification(target: str, title: str, body: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return send_notification(target, title, body, payload)


def _send_telegram_notification(target: str, title: str, body: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    settings = get_settings()
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return _record_notification(
            "telegram",
            target,
            title,
            body,
            payload,
            "failed",
            "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required",
        )

    messages = _telegram_messages(title, body, payload)
    error = None
    status = "sent"
    try:
        for message in messages:
            response = httpx.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json={
                    "chat_id": settings.telegram_chat_id,
                    "text": message,
                    "disable_web_page_preview": True,
                },
                timeout=TELEGRAM_SEND_TIMEOUT_SECONDS,
            )
            data = response.json()
            if response.status_code != 200 or not data.get("ok"):
                status = "failed"
                error = data.get("description") or f"Telegram HTTP {response.status_code}"
                break
    except Exception as exc:
        status = "failed"
        error = f"{type(exc).__name__}: {exc}"

    return _record_notification("telegram", target, title, body, payload, status, error)


def _telegram_messages(title: str, body: str, payload: Dict[str, Any]) -> list:
    message = _format_telegram_message(title, body, payload)
    return _split_telegram_message(message)


def _format_telegram_message(title: str, body: str, payload: Dict[str, Any]) -> str:
    lines = [title, "", body]
    if payload:
        source = payload.get("source")
        ticker = payload.get("ticker")
        report_id = payload.get("report_id")
        details = []
        if ticker:
            details.append(f"종목: {ticker}")
        if report_id:
            details.append(f"리포트 ID: {report_id}")
        if source:
            details.append(f"출처: {source}")
        if details:
            lines.extend(["", *details])
        report_markdown = payload.get("report_markdown")
        if report_markdown:
            lines.extend(["", "----- 리포트 본문 -----", report_markdown])
    return "\n".join(line for line in lines if line is not None)


def _split_telegram_message(message: str) -> list:
    if len(message) <= TELEGRAM_MAX_MESSAGE_LENGTH:
        return [message]

    chunks = []
    current = []
    current_length = 0
    for line in message.splitlines():
        line_length = len(line) + 1
        if current and current_length + line_length > TELEGRAM_MAX_MESSAGE_LENGTH:
            chunks.append("\n".join(current))
            current = []
            current_length = 0
        if line_length > TELEGRAM_MAX_MESSAGE_LENGTH:
            for index in range(0, len(line), TELEGRAM_MAX_MESSAGE_LENGTH):
                part = line[index : index + TELEGRAM_MAX_MESSAGE_LENGTH]
                if current:
                    chunks.append("\n".join(current))
                    current = []
                    current_length = 0
                chunks.append(part)
            continue
        current.append(line)
        current_length += line_length
    if current:
        chunks.append("\n".join(current))

    total = len(chunks)
    if total <= 1:
        return chunks
    return [f"[{index + 1}/{total}]\n{chunk}" for index, chunk in enumerate(chunks)]


def _record_notification(
    channel: str,
    target: str,
    title: str,
    body: str,
    payload: Dict[str, Any],
    status: str,
    error: str,
) -> Dict[str, Any]:
    return db.insert(
        "notification_log",
        {
            "channel": channel,
            "target": target,
            "title": title,
            "body": body,
            "payload": payload,
            "status": status,
            "error": error,
            "created_at": db.utc_now(),
        },
    )
