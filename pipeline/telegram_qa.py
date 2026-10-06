"""AI 뉴스 봇에게 온 사용자 질문에 답한다. GitHub Actions telegram-qa.yml이 5분마다 실행한다.

- python telegram_qa.py --check : 처리할 메시지가 있는지만 확인해 GITHUB_OUTPUT에 pending=true/false를 쓴다
  (없으면 Claude Code 설치 없이 바로 끝내서 사용량을 아낀다)
- python telegram_qa.py         : 새 질문마다 최근 브리핑 + 웹 검색으로 답을 써서 답장으로 보낸다

TELEGRAM_CHAT_ID(사용자 본인)에서 온 메시지에만 답하고, 다른 사람 메시지는 읽음 처리만 한다.
처리한 메시지는 getUpdates의 offset으로 확인 처리해 텔레그램 쪽 대기열에서 지운다.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from claude_cli import run_claude
from send_telegram import _call, send_text

BOT = "news"
KST = timezone(timedelta(hours=9))
DATA_DIR = Path(__file__).resolve().parent.parent / "docs" / "data"
RECENT_BRIEFINGS = 3  # 질문 맥락으로 넘길 최근 브리핑 일수
MAX_PER_RUN = 3  # 한 번 실행에 답할 최대 질문 수 (나머지는 다음 실행에)
ANSWER_LIMIT = 3800  # 텔레그램 한 메시지 한도(4096) 안쪽

SYSTEM = """당신은 사용자에게 매일 AI 뉴스 브리핑을 보내는 텔레그램 봇입니다. 사용자가 브리핑을 보고
궁금한 점을 물었습니다. 아래 최근 브리핑과 필요하면 WebSearch로 찾은 최신 정보를 바탕으로 답합니다.

[답하는 방식]
- 읽는 사람은 중학생이라고 생각하고 씁니다. 한 문장에 한 내용, 40자 안팎으로 짧게 끊습니다.
  주어를 앞에 두고, 번역투("~하는 것은 ~하게 만든다", 명사 덩어리)를 쓰지 않습니다.
- 어려운 말은 쉬운 말로 바꾸고, 바꾸기 어려운 이름은 바로 뒤에 짧은 풀이를 붙입니다.
- "3번 자세히"처럼 짧게 물으면, 사용자가 답장한 브리핑(또는 가장 최근 브리핑)의 해당 기사를 뜻합니다.
- 뉴스를 자세히 묻는 질문이면 아래 순서로 씁니다(각 부분은 표시어로 시작하고 덩어리마다 줄바꿈):
  📌 무슨 일? (브리핑보다 더 자세히: 경과, 관련 회사·사람·수치, 근거, 아직 모르는 것, 대응)
  🧭 배경 (이해에 꼭 필요한 것만)
  💡 쉽게 말하면 (일상 비유 + 나한테 무슨 의미인지)
  💬 ENTP 한마디 (반말만이 아니라 성격이 드러나게: 뻔한 해석 뒤집기, 도발적 질문,
     악마의 변호인, 엉뚱하지만 정확한 비유, 다른 흐름과 엮기 중 두 가지 이상)
  짧은 질문(예: "엔비디아가 뭐야?")에는 형식에 얽매이지 말고 짧고 쉽게 답하고 ENTP 한마디만 붙입니다.
- 말투는 친한 친구 같은 반말입니다.
- 사실은 정확히 지킵니다. 확인 못 한 내용은 "(추정)" 또는 "아직 확인 안 됨"이라고 씁니다.
  사건 날짜는 "지난 6일(현지시간)"처럼 밝힙니다.
- 끝에 "출처:" 줄을 두고 근거로 쓴 URL을 최대 3개 적습니다.
- 마크다운 문법(#, **, 표)은 쓰지 않습니다. 전체 3500자 이내.
"""


def _allowed_chat() -> str:
    return os.environ["TELEGRAM_CHAT_ID"].strip()


def _pending() -> list[dict]:
    """사용자 본인이 보낸 글자 메시지 업데이트 목록 (다른 업데이트도 함께 반환해 읽음 처리에 쓴다)."""
    return _call(BOT, "getUpdates", timeout=0, allowed_updates=["message"])


def _is_question(update: dict) -> bool:
    msg = update.get("message") or {}
    text = (msg.get("text") or "").strip()
    return str((msg.get("chat") or {}).get("id")) == _allowed_chat() and bool(text) and text != "/start"


def _ack(update_id: int) -> None:
    """이 update_id까지 처리 완료로 표시 (텔레그램 대기열에서 지워짐)."""
    _call(BOT, "getUpdates", offset=update_id + 1, timeout=0)


def _recent_briefings() -> list[dict]:
    files = sorted(DATA_DIR.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].json"), reverse=True)
    out = []
    for f in files[:RECENT_BRIEFINGS]:
        d = json.loads(f.read_text(encoding="utf-8"))
        out.append({
            "briefing_date": f.stem,
            "telegram_message": d.get("message_text", ""),
            "articles": [
                {"rank": a.get("rank"), "event_date": a.get("event_date"), "title": a.get("title"),
                 "body": a.get("body"), "sources": a.get("sources", [])}
                for a in d.get("articles", [])
            ],
        })
    return out


def _answer(msg: dict) -> str:
    replied = (msg.get("reply_to_message") or {}).get("text") or ""
    prompt = (
        f"지금 시각(KST): {datetime.now(KST):%Y-%m-%d %H:%M}\n\n"
        f"사용자 질문: {msg['text'].strip()}\n\n"
        + (f"사용자가 답장한 봇 메시지:\n{replied}\n\n" if replied else "")
        + "최근 브리핑 (최신순):\n"
        + json.dumps(_recent_briefings(), ensure_ascii=False, indent=2)
        + "\n\n위 규칙에 따라 답을 쓰세요."
    )
    envelope = run_claude(prompt=prompt, system_prompt=SYSTEM, allowed_tools="WebSearch", timeout=900)
    text = (envelope.get("result") or "").strip()
    return text[:ANSWER_LIMIT] if text else "답을 만들지 못했어. 조금 다르게 다시 물어봐 줄래?"


def check() -> None:
    pending = any(_is_question(u) for u in _pending())
    print(f"[telegram_qa] 처리할 질문: {'있음' if pending else '없음'}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"pending={'true' if pending else 'false'}\n")


def main() -> None:
    answered = 0
    for update in _pending():
        if not _is_question(update):
            _ack(update["update_id"])  # 다른 사람 메시지·/start 등은 읽음 처리만
            continue
        if answered >= MAX_PER_RUN:
            break  # 나머지는 다음 실행에서
        msg = update["message"]
        print(f"[telegram_qa] 질문: {msg['text'][:80]}")
        try:
            send_text("🔎 찾아보는 중이야, 1~2분만 기다려!", bot=BOT, reply_to=msg["message_id"])
            send_text(_answer(msg), bot=BOT, reply_to=msg["message_id"])
        except Exception as exc:  # noqa: BLE001 - 실패해도 같은 질문이 무한 반복되지 않게 읽음 처리
            print(f"[telegram_qa] 답변 실패: {exc}", file=sys.stderr)
            send_text("앗, 답을 만들다가 문제가 생겼어. 잠시 후에 다시 물어봐 줘🙏", bot=BOT, reply_to=msg["message_id"])
        _ack(update["update_id"])
        answered += 1
    print(f"[telegram_qa] 답변 {answered}건")


if __name__ == "__main__":
    check() if "--check" in sys.argv else main()
