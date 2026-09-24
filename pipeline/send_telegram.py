"""텔레그램 봇으로 메시지를 보낸다.
TELEGRAM_CHAT_ID가 없으면 봇에게 온 최근 메시지(getUpdates)에서 chat_id를 찾아 쓰고,
GitHub Secret TELEGRAM_CHAT_ID로 저장한다 (GH_PAT, GITHUB_REPOSITORY 환경변수 필요).
"""
from __future__ import annotations

import os
import sys

import requests

from kakao_token import _update_github_secret

API = "https://api.telegram.org/bot{token}/{method}"


def _call(method: str, **payload) -> dict:
    token = os.environ["TELEGRAM_BOT_TOKEN"].strip()
    resp = requests.post(API.format(token=token, method=method), json=payload, timeout=15)
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"텔레그램 {method} 실패 ({resp.status_code}): {data.get('description')}")
    return data["result"]


def _discover_chat_id() -> str:
    updates = _call("getUpdates")
    for u in reversed(updates):
        chat = (u.get("message") or {}).get("chat") or {}
        if chat.get("type") == "private":
            return str(chat["id"])
    raise RuntimeError(
        "봇에게 온 메시지가 없어 chat_id를 찾지 못했습니다. "
        "텔레그램에서 봇 대화방에 아무 메시지나 보낸 뒤 다시 실행하세요 (24시간 이내 메시지만 조회됨)."
    )


def get_chat_id() -> str:
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if chat_id:
        return chat_id
    chat_id = _discover_chat_id()
    print("[send_telegram] chat_id를 찾아 GitHub Secret TELEGRAM_CHAT_ID로 저장합니다.", file=sys.stderr)
    _update_github_secret("TELEGRAM_CHAT_ID", chat_id)
    return chat_id


def send_text_with_button(text: str, button_title: str, url: str) -> dict:
    return _call(
        "sendMessage",
        chat_id=get_chat_id(),
        text=text,
        disable_web_page_preview=True,
        reply_markup={"inline_keyboard": [[{"text": button_title, "url": url}]]},
    )
