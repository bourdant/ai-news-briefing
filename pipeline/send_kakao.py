"""카카오톡 '나에게 보내기'(talk_message)로 브리핑 요약 + 링크 버튼을 전송한다."""
from __future__ import annotations

import json
import os
import sys

import requests

from kakao_token import refresh_access_token

SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"


def send_text_with_button(text: str, button_title: str, url: str) -> dict:
    access_token = refresh_access_token()
    template_object = {
        "object_type": "text",
        "text": text,
        "link": {"web_url": url, "mobile_web_url": url},
        "button_title": button_title,
    }
    resp = requests.post(
        SEND_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        data={"template_object": json.dumps(template_object, ensure_ascii=False)},
        timeout=15,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"카카오톡 전송 실패 ({resp.status_code}): {resp.text}")
    return resp.json()


def send_briefing(date: str, kakao_text: str) -> dict:
    page_base = os.environ["PAGE_BASE_URL"].rstrip("/")
    url = f"{page_base}/{date}/index.html"
    return send_text_with_button(kakao_text, "전체 브리핑 보기", url)


def send_test_message() -> dict:
    page_base = os.environ.get("PAGE_BASE_URL", "https://example.com").rstrip("/")
    return send_text_with_button(
        "✅ AI 뉴스 브리핑 카카오톡 연동 테스트입니다.\n이 메시지가 보이면 설정이 정상 완료된 거예요!",
        "테스트 페이지 열기",
        page_base,
    )


if __name__ == "__main__":
    if "--test" in sys.argv:
        result = send_test_message()
        print("테스트 메시지 전송 완료:", result)
    else:
        if len(sys.argv) < 3:
            print("사용법: python send_kakao.py <date YYYY-MM-DD> <kakao_text> | python send_kakao.py --test")
            raise SystemExit(1)
        print(send_briefing(sys.argv[1], sys.argv[2]))
