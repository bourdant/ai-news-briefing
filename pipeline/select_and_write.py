"""RSS 후보 + 웹 검색 보완을 Claude Code CLI(구독 기반) 한 번의 호출에 넘겨
선별·작성까지 맡긴다.

입력: collect.py가 만든 후보 리스트, 웹 검색 보완이 필요한 소스 리스트
출력: docs/data/YYYY-MM-DD.json 에 쓸 구조화된 dict
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone

from claude_cli import run_claude

KST = timezone(timedelta(hours=9))

CATEGORIES = [
    "model_release",  # 신규 모델/주요 기능 발표
    "business",        # 사업, 주가, 투자, 인수합병
    "policy",           # 정책, 규제, 소송
    "opensource",       # 오픈소스 공개
    "safety",           # 안전성, 논란, 사고
    "product",          # 제품/서비스 업데이트
    "research",         # 연구 결과
    "other",
]

JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "date": {"type": "string"},
        "one_liner": {"type": "string"},
        "kakao_text": {"type": "string"},
        "selection_note": {"type": ["string", "null"]},
        "articles": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "rank": {"type": "integer"},
                    "title": {"type": "string"},
                    "category": {"type": "string", "enum": CATEGORIES},
                    "is_official_announcement": {"type": "boolean"},
                    "source_count": {"type": "integer"},
                    "sources": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "url": {"type": "string"},
                            },
                            "required": ["name", "url"],
                        },
                    },
                    "body": {"type": "string"},
                    "metric_note": {"type": ["string", "null"]},
                },
                "required": [
                    "id", "rank", "title", "category", "is_official_announcement",
                    "source_count", "sources", "body",
                ],
            },
        },
    },
    "required": ["date", "one_liner", "kakao_text", "articles"],
}

SYSTEM_PROMPT = f"""당신은 한국어로 AI 뉴스 브리핑을 작성하는 편집자입니다.
아래 규칙을 정확히 지켜서, 주어진 JSON 스키마에 맞는 결과만 만들어내세요.

[선별 규칙]
- 2곳 이상의 서로 다른 소스(RSS 후보 또는 당신이 WebSearch로 확인한 소스)에서
  다룬 소식만 남깁니다.
- 예외: OpenAI, Anthropic, Google DeepMind 공식 블로그의 "신규 모델 출시" 또는
  "주요 기능 발표"는 다른 곳에서 다루지 않았어도 무조건 포함합니다.
  이 경우 is_official_announcement=true, sources는 공식 블로그 1개만 있어도 됩니다.
- 하루 최대 5개, is_official_announcement 예외를 제외하면 2곳 이상 교차 확인된 것만.
- 기준을 통과한 소식이 5개 미만이면 억지로 채우지 말고 개수를 줄이세요. 대신 남는
  분량은 가장 중요한(rank=1) 기사의 body 설명을 더 길고 풍부하게 써서 채우세요.
- 중요도 순으로 rank 1부터 정렬하세요.
- 매체마다 관련 수치(투자액, 이용자 수, 점유율 등)의 기준이 서로 다르면
  metric_note 필드에 "A매체는 ~기준, B매체는 ~기준"처럼 각각 명시하세요.
  해당 없으면 null.
- 웹 검색 보완이 필요하다고 안내된 소스는 반드시 WebSearch 도구로 오늘
  발행된 글이 있는지 확인하세요. 확인되면 후보에 포함하고, 다른 소스와
  교차 확인되는지도 함께 판단하세요.
- 애매하게 2곳에서 다뤘는지 판단이 안 서는 RSS 후보는 WebSearch로 추가 확인하세요.

[작성 규칙 - 매우 중요]
- 중학생도 이해할 수 있게 씁니다. 전문용어는 쓰지 않고, 꼭 필요하면 바로 뒤 괄호나
  쉼표로 쉬운 말을 붙입니다.
- 회사 이름이 처음 나올 때는 "ChatGPT를 만든 OpenAI"처럼 그 회사가 뭘 하는 곳인지
  붙여서 설명합니다.
- 각 기사 body는 "무슨 일이 있었는지 → 이게 왜 대단하거나 문제인지" 순서로 쓰고,
  반드시 일상생활 비유를 하나씩 넣습니다 (예: 경쟁사 동시 출시 = "경쟁 카페 두 곳이
  같은 날 신메뉴를 낸 것", 사용료 = "쓴 만큼 내는 전기요금").
- 말투는 친근한 존댓말입니다.
- one_liner: 그날 소식 전체를 묶는 한 문장. 친근한 존댓말.
- kakao_text: 카카오톡에 보낼 본문으로, 반드시 200자(공백 포함) 이내여야 합니다.
  형식은 "오늘의 한 줄: <one_liner 요약>" 줄바꿈 후 각 기사 제목을 줄바꿈으로 나열한
  목록만 담습니다. 링크나 버튼 문구는 절대 넣지 마세요(버튼은 별도로 붙습니다).
"""


def _build_user_prompt(candidates: list, needs_search: list[dict]) -> str:
    today_kst = datetime.now(KST).strftime("%Y-%m-%d")
    cand_payload = [
        {
            "title": c.title,
            "url": c.url,
            "source": c.source_name,
            "source_kind": c.source_kind,
            "published": c.published,
            "summary": c.summary,
        }
        for c in candidates
    ]
    search_targets = [
        {
            "name": s["name"],
            "homepage": s.get("homepage") or s.get("rss"),
            "kind": s["kind"],
        }
        for s in needs_search
    ]
    return (
        f"오늘 날짜(KST): {today_kst}\n\n"
        f"RSS로 수집된 후보 뉴스 ({len(cand_payload)}건):\n"
        f"{json.dumps(cand_payload, ensure_ascii=False, indent=2)}\n\n"
        f"웹 검색으로 보완 확인이 필요한 소스:\n"
        f"{json.dumps(search_targets, ensure_ascii=False, indent=2)}\n\n"
        "위 규칙에 따라 선별하고 작성하세요."
    )


def select_and_write(candidates: list, needs_search: list[dict]) -> dict:
    today_kst = datetime.now(KST).strftime("%Y-%m-%d")
    user_prompt = _build_user_prompt(candidates, needs_search)

    envelope = run_claude(
        prompt=user_prompt,
        system_prompt=SYSTEM_PROMPT,
        allowed_tools="WebSearch",
        json_schema=JSON_SCHEMA,
    )

    data = envelope.get("structured_output")
    if not data:
        raise RuntimeError(f"Claude 응답에 structured_output이 없습니다: {envelope.get('result')}")

    if len(data.get("kakao_text", "")) > 200:
        print(
            f"[select_and_write] 경고: kakao_text가 {len(data['kakao_text'])}자로 200자를 "
            "초과했습니다. 잘라냅니다.",
            file=sys.stderr,
        )
        data["kakao_text"] = data["kakao_text"][:200]

    data.setdefault("date", today_kst)
    for i, art in enumerate(data.get("articles", []), start=1):
        art.setdefault("rank", i)

    return data


if __name__ == "__main__":
    from collect import collect_all

    cands, missing = collect_all()
    result = select_and_write(cands, missing)
    print(json.dumps(result, ensure_ascii=False, indent=2))
