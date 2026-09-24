"""일일 브리핑 파이프라인 진입점. GitHub Actions daily-briefing.yml에서 호출한다.
수집 -> 선별/작성(Claude) -> 페이지 렌더링 -> 텔레그램 전송까지 한 번에 수행한다.
실제 git commit/push는 워크플로 쪽에서 처리한다 (이 스크립트는 파일만 만든다).
"""
from __future__ import annotations

import json
import sys

from collect import collect_all
from render_page import render
from select_and_write import select_and_write
from send_telegram import send_briefing


def main() -> None:
    print("[run_daily] 1/4 RSS 수집 중...")
    candidates, needs_search = collect_all()
    print(f"[run_daily] 후보 {len(candidates)}건, 웹 검색 보완 {len(needs_search)}개 소스")

    print("[run_daily] 2/4 Claude로 선별/작성 중...")
    data = select_and_write(candidates, needs_search)
    print(f"[run_daily] 선정된 기사 {len(data.get('articles', []))}건")

    print("[run_daily] 3/4 페이지 렌더링 중...")
    day_dir = render(data)
    print(f"[run_daily] 렌더링 완료: {day_dir}")

    print("[run_daily] 4/4 텔레그램 전송 중...")
    send_briefing(data["date"], data["message_text"])
    print("[run_daily] 텔레그램 전송 완료")

    print(json.dumps({"date": data["date"], "articles": len(data.get("articles", []))}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"[run_daily] 실패: {exc}", file=sys.stderr)
        raise
