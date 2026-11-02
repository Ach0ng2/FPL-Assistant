"""Integrasi Telegram Bot untuk kirim notifikasi rekomendasi sebelum deadline."""

from __future__ import annotations

import httpx

from .config import Settings


def send_telegram_message(settings: Settings, message: str) -> bool:
    """Mengirim pesan teks (markdown/HTML) ke Telegram Bot."""
    if not settings.telegram_token or not settings.telegram_chat_id:
        return False

    url = f"https://api.telegram.org/bot{settings.telegram_token}/sendMessage"
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }

    try:
        resp = httpx.post(url, json=payload, timeout=15.0)
        resp.raise_for_status()
        return True
    except Exception as exc:
        print(f"[Telegram Error] Gagal kirim pesan: {exc}")
        return False
