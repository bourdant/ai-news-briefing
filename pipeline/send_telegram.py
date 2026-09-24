"""텔레그램 봇으로 메시지를 보낸다.

- bot="default": TELEGRAM_BOT_TOKEN (주간 데이터랩 순위)
- bot="news": TELEGRAM_NEWS_BOT_TOKEN (AI 뉴스 브리핑). 아직 없으면 TELEGRAM_BOT_TOKEN으로 대신 보낸다.

받는 사람은 TELEGRAM_CHAT_ID. 1:1 대화의 chat_id는 내 텔레그램 사용자 ID라서 봇이 달라도 같다
(단, 각 봇 대화방에서 한 번은 먼저 메시지를 보내야 봇이 보낼 수 있다).
TELEGRAM_CHAT_ID가 없으면 봇에게 온 최근 메시지(getUpdates)에서 찾아 쓰고 GitHub Secret으로 저장한다.
"""
from __future__ import annotations

import os
import sys

import requests

from github_secret import update_github_secret

API = "https://api.telegram.org/bot{token}/{method}"
TEXT_LIMIT = 4096  # 텔레그램 메시지 최대 길이


def _token(bot: str) -> str:
    if bot == "news":
        token = os.environ.get("TELEGRAM_NEWS_BOT_TOKEN", "").strip()
        if token:
            return token
        print("[send_telegram] TELEGRAM_NEWS_BOT_TOKEN이 없어 기본 봇으로 보냅니다.", file=sys.stderr)
    return os.environ["TELEGRAM_BOT_TOKEN"].strip()


def _call(bot: str, method: str, **payload) -> dict:
    resp = requests.post(API.format(token=_token(bot), method=method), json=payload, timeout=15)
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"텔레그램 {method} 실패 ({resp.status_code}): {data.get('description')}")
    return data["result"]


def _discover_chat_id(bot: str) -> str:
    updates = _call(bot, "getUpdates")
    for u in reversed(updates):
        chat = (u.get("message") or {}).get("chat") or {}
        if chat.get("type") == "private":
            return str(chat["id"])
    raise RuntimeError(
        "봇에게 온 메시지가 없어 chat_id를 찾지 못했습니다. "
        "텔레그램에서 봇 대화방에 아무 메시지나 보낸 뒤 다시 실행하세요 (24시간 이내 메시지만 조회됨)."
    )


def get_chat_id(bot: str = "default") -> str:
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if chat_id:
        return chat_id
    chat_id = _discover_chat_id(bot)
    print("[send_telegram] chat_id를 찾아 GitHub Secret TELEGRAM_CHAT_ID로 저장합니다.", file=sys.stderr)
    update_github_secret("TELEGRAM_CHAT_ID", chat_id)
    return chat_id


def send_text(text: str, button_title: str | None = None, url: str | None = None,
              bot: str = "default") -> dict:
    if len(text) > TEXT_LIMIT:
        text = text[: TEXT_LIMIT - 1] + "…"
    payload = {"chat_id": get_chat_id(bot), "text": text, "disable_web_page_preview": True}
    if button_title and url:
        payload["reply_markup"] = {"inline_keyboard": [[{"text": button_title, "url": url}]]}
    return _call(bot, "sendMessage", **payload)


def send_text_with_button(text: str, button_title: str, url: str, bot: str = "default") -> dict:
    return send_text(text, button_title, url, bot=bot)


def send_briefing(date: str, text: str) -> dict:
    page_base = os.environ["PAGE_BASE_URL"].rstrip("/")
    return send_text(text, "전체 브리핑 보기", f"{page_base}/{date}/index.html", bot="news")


if __name__ == "__main__":
    # 사용법: python send_telegram.py <텍스트 파일> [default|news]
    path = sys.argv[1]
    bot = sys.argv[2] if len(sys.argv) > 2 else "default"
    with open(path, encoding="utf-8") as f:
        print(send_text(f.read().strip(), bot=bot))
