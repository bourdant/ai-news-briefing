"""RSS 후보 + 웹 검색 보완을 Claude API 한 번의 호출에 넘겨 선별·작성까지 맡긴다.

입력: collect.py가 만든 후보 리스트, 웹 검색 보완이 필요한 소스 리스트
출력: docs/data/YYYY-MM-DD.json 에 쓸 구조화된 dict (JSON 스키마는 아래 PROMPT 참고)
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

from anthropic import Anthropic

KST = timezone(timedelta(hours=9))
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")

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

SYSTEM_PROMPT = f"""당신은 한국어로 AI 뉴스 브리핑을 작성하는 편집자입니다.
아래 규칙을 정확히 지켜서, 오직 하나의 JSON 객체만 출력하세요. 마크다운 코드펜스나
설명 문장을 앞뒤에 절대 붙이지 마세요. 출력은 반드시 유효한 JSON이어야 합니다.

[선별 규칙]
- 2곳 이상의 서로 다른 소스(RSS 후보 또는 당신이 web_search로 확인한 소스)에서 다룬
  소식만 남깁니다.
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
- 웹 검색 보완이 필요하다고 안내된 소스는 반드시 web_search 도구로 오늘
  ({{today_kst}}, KST) 발행된 글이 있는지 확인하세요. 확인되면 후보에 포함하고,
  다른 소스와 교차 확인되는지도 함께 판단하세요.
- 애매하게 2곳에서 다뤘는지 판단이 안 서는 RSS 후보는 web_search로 추가 확인하세요.

[작성 규칙 - 매우 중요]
- 중학생도 이해할 수 있게 씁니다. 전문용어는 쓰지 않고, 꼭 필요하면 바로 뒤 괄호나
  쉼표로 쉬운 말을 붙입니다.
- 회사 이름이 처음 나올 때는 "ChatGPT를 만든 OpenAI"처럼 그 회사가 뭘 하는 곳인지
  붙여서 설명합니다.
- 각 기사 body는 "무슨 일이 있었는지 → 이게 왜 대단하거나 문제인지" 순서로 쓰고,
  반드시 일상생활 비유를 하나씩 넣습니다 (예: 경쟁사 동시 출시 = "경쟁 카페 두 곳이
  같은 날 신메뉴를 낸 것", 사용료 = "쓴 만큼 내는 전기요금").
- 말투는 친근한 존댓말입니다.
- category는 다음 중 하나: {", ".join(CATEGORIES)}
- one_liner: 그날 소식 전체를 묶는 한 문장. 친근한 존댓말.
- kakao_text: 카카오톡에 보낼 본문으로, 반드시 200자(공백 포함) 이내여야 합니다.
  형식은 "오늘의 한 줄: <one_liner 요약>" 줄바꿈 후 각 기사 제목을 줄바꿈으로 나열한
  목록만 담습니다. 링크나 버튼 문구는 절대 넣지 마세요(버튼은 별도로 붙습니다).

[출력 JSON 스키마]
{{
  "date": "YYYY-MM-DD",
  "one_liner": "string",
  "kakao_text": "string (<=200자)",
  "selection_note": "string 또는 null (5개 미만으로 줄인 이유 등을 설명할 때만)",
  "articles": [
    {{
      "id": "kebab-case-ascii-slug",
      "rank": 1,
      "title": "string (한국어 헤드라인)",
      "category": "위 카테고리 중 하나",
      "is_official_announcement": true,
      "source_count": 2,
      "sources": [{{"name": "string", "url": "string"}}],
      "body": "string (여러 문단 가능, 비유 포함)",
      "metric_note": "string 또는 null"
    }}
  ]
}}
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
        "위 규칙에 따라 선별하고 작성한 뒤, JSON 객체 하나만 출력하세요."
    )


def _extract_json(text: str) -> dict:
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"응답에서 JSON을 찾을 수 없습니다: {text[:500]}")
    return json.loads(text[start : end + 1])


def select_and_write(candidates: list, needs_search: list[dict]) -> dict:
    client = Anthropic()
    today_kst = datetime.now(KST).strftime("%Y-%m-%d")
    system = SYSTEM_PROMPT.replace("{today_kst}", today_kst)
    user_prompt = _build_user_prompt(candidates, needs_search)

    response = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        temperature=0.3,
        system=system,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 8}],
        messages=[{"role": "user", "content": user_prompt}],
    )

    text_blocks = [b.text for b in response.content if getattr(b, "type", "") == "text"]
    full_text = "\n".join(text_blocks)
    if not full_text.strip():
        raise RuntimeError("Claude 응답에 텍스트가 없습니다 (web_search만 반환됨)")

    data = _extract_json(full_text)

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
