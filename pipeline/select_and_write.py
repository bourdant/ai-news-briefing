"""RSS 후보 + 웹 검색 보완을 Claude Code CLI(구독 기반) 한 번의 호출에 넘겨
선별·작성까지 맡긴다.

입력: collect.py가 만든 후보 리스트, 웹 검색 보완이 필요한 소스 리스트
출력: docs/data/YYYY-MM-DD.json 에 쓸 구조화된 dict
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

from claude_cli import run_claude

KST = timezone(timedelta(hours=9))
DATA_DIR = Path(__file__).resolve().parent.parent / "docs" / "data"
RECENT_DAYS = 3  # 중복 판단에 넘길 최근 브리핑 일수
MESSAGE_LIMIT = 2000  # 텔레그램 본문 길이 (텔레그램 자체 한도는 4096자)

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
        "message_text": {"type": "string"},
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
                    "event_date": {"type": "string"},
                    "followup_note": {"type": ["string", "null"]},
                    "metric_note": {"type": ["string", "null"]},
                },
                "required": [
                    "id", "rank", "title", "category", "is_official_announcement",
                    "source_count", "sources", "body", "event_date",
                ],
            },
        },
    },
    "required": ["date", "one_liner", "message_text", "articles"],
}

SYSTEM_PROMPT = f"""당신은 한국어로 AI 뉴스 브리핑을 작성하는 편집자입니다.
아래 규칙을 정확히 지켜서, 주어진 JSON 스키마에 맞는 결과만 만들어내세요.

[선별 규칙 - 중요도는 주요 언론사의 '배치 순위'로 판단]
- 아래 "주요 언론사 배치 순위"는 NBC 뉴스 AI 섹션, ABC 뉴스 기술 섹션, Techmeme 첫 화면,
  조선일보 테크·IT 섹션에서 편집자가 위에서부터 배치한 순서입니다(1위 = 맨 위).
  중요도는 당신의 감이 아니라 이 순위로 정합니다:
  · 여러 사이트에서 위쪽에 걸린 소식일수록 중요합니다 (같은 사건이면 영어·한국어 제목이
    달라도 같은 소식으로 묶어서 셉니다).
  · 한 사이트에서만 나왔다면 그 사이트의 상위권(대략 5위 안)일 때 후보가 됩니다.
  · 순위 목록의 AI와 직접 관련 없는 기사(일반 주식·연예 등)는 제외합니다.
- 고른 소식의 세부 내용은 RSS 후보와 WebSearch로 확인합니다. 순위 목록에 없는 RSS 후보는
  원칙적으로 고르지 않습니다. 예외: OpenAI, Anthropic, Google DeepMind 공식 블로그의
  "신규 모델 출시"·"주요 기능 발표"는 순위와 상관없이 포함할 수 있습니다
  (is_official_announcement=true, sources는 공식 블로그 1개만 있어도 됨).
- 출처(sources) 규칙:
  · 가능하면 원래 보도한 매체(로이터, 블룸버그, NBC, 파이낸셜타임스 등)를 적습니다.
  · AI타임스처럼 해외 기사를 번역·인용한 기사는 원문과 같은 1곳으로 셉니다. 원문 매체를
    확인할 수 있으면 원문 매체를 출처로 적고, AI타임스는 국내 소식이거나 국내 반응을
    따로 취재한 경우에만 독립 출처로 적습니다.
  · source_count는 서로 다른 원래 보도 매체의 수입니다.
- 하루 최대 5개. 기준을 통과한 소식이 5개 미만이면 억지로 채우지 말고 개수를 줄이세요.
- rank는 위 배치 순위 기준의 중요도 순으로 1부터 매깁니다.
- event_date: 그 일이 실제로 일어난(발표·발언·사고가 있었던) 날짜를 "YYYY-MM-DD"로
  적습니다. 기사가 나온 날이 아니라 사건 날짜이며, 해외 소식은 현지 날짜 기준입니다.
  소스에서 날짜를 확인하고, 애매하면 WebSearch로 확인하세요.
- 중복 판단: 아래에 최근 며칠 치 브리핑 목록을 줍니다. 이미 다룬 소식은 원칙적으로
  다시 넣지 않습니다. 다만 (1) 아주 중요하거나 (2) 그 뒤 새로운 진전(후속 발표, 반응,
  수치 변화 등)이 있으면 다시 넣을 수 있고, 이때 followup_note에 "9/24 브리핑에서 다룬
  소식의 후속 — 새로 나온 내용: …"처럼 무엇이 새로워졌는지 한 문장으로 적습니다.
  새 소식이면 followup_note는 null.
- 매체마다 관련 수치(투자액, 이용자 수, 점유율 등)의 기준이 서로 다르면
  metric_note 필드에 "A매체는 ~기준, B매체는 ~기준"처럼 각각 명시하세요.
  해당 없으면 null.
- 웹 검색 보완이 필요하다고 안내된 소스는 반드시 WebSearch 도구로 오늘
  발행된 글이 있는지 확인하세요. 확인되면 후보에 포함하고, 다른 소스와
  교차 확인되는지도 함께 판단하세요.
- 애매하게 2곳에서 다뤘는지 판단이 안 서는 RSS 후보는 WebSearch로 추가 확인하세요.

[작성 규칙 - 매우 중요]
읽는 사람은 중학생이라고 생각하고 씁니다. 사실 전달 부분과 ENTP 코멘트 부분을 확실히
나눕니다. 사실 부분은 "쉽고 짧게", ENTP 부분은 "성격이 확 드러나게"가 목표입니다.

[문장 규칙 - 사실 전달 부분]
- 한 문장에는 한 가지 내용만 담습니다. 40자 안팎을 넘기면 두 문장으로 나눕니다.
- 주어를 문장 앞에 둡니다. "누가 → 무엇을 했다" 순서로 씁니다.
- 번역투와 명사 덩어리를 쓰지 않습니다. 예:
  · (나쁨) "규제가 '중국 AI 억제'라는 원래 목표를 온전히 달성하고 있는지 다시 생각하게 만들어."
    (좋음) "미국은 중국 AI를 막으려고 칩 수출을 막았어. 그런데 중국 AI는 오히려 몸값이 올랐어. 그럼 이 규제, 효과가 있는 걸까?"
  · (나쁨) "보안팀에게 제한을 풀어준 클로드를 빌려주는 '사이버 검증 프로그램'을 3단계 등급 체계로 확장했어."
    (좋음) "앤트로픽이 보안 전문가들한테 특별한 클로드를 빌려주고 있어. 해킹을 막는 연구에 쓰라고 안전장치를 일부 풀어준 버전이야. 이번에 빌려주는 대상을 3단계로 나눠서 더 넓혔어."
  · 피할 표현: "~하는 것은 ~하게 만든다", "~에 있어서", "~로 인해", "~의 ~의 ~",
    "~적인", 한 문장에 쉼표 3개 이상.
- 어려운 말은 쉬운 말로 바꾸고, 바꾸기 어려운 이름은 바로 뒤에 짧은 풀이를 붙입니다:
  · 연내 → 올해 안에 / 당초 → 원래 / 상향 → 올림 / 벤치마크 → 성능 시험 점수
  · 파라미터 → AI 두뇌 크기를 나타내는 숫자 / API → 다른 앱이 AI를 가져다 쓰는 연결 통로
  · 에이전트 → 시키면 알아서 여러 단계를 처리하는 AI 비서 / 추론 → 생각해서 답을 찾는 능력
  · 크리스퍼 → 크리스퍼(DNA를 잘라내고 고치는 '유전자 가위' 기술)
- 회사 이름이 처음 나오면 "챗GPT를 만든 오픈AI"처럼 뭘 하는 회사인지 붙입니다.
- 배경 설명: 이 소식을 이해하는 데 꼭 필요한 배경만 짧게 넣습니다. 그 기사와 직접 관련
  없는 배경(다른 기사에 어울리는 배경)을 끼워 넣지 않습니다. 배경이 필요 없으면 넣지 않습니다.
  · 누가 누구를 비판했다 → 비판받은 쪽이 전에 무슨 말·행동을 했는지, 왜 부딪히는지
  · 협약·약속 → 누가 누구에게 무엇을 약속했는지, 강제력이 있는지
  필요하면 WebSearch로 배경을 확인합니다.

[ENTP 코멘트 규칙 - 기사마다 따로]
- 반말만으로는 ENTP가 아닙니다. 코멘트마다 아래 중 최소 두 가지를 담습니다:
  · 뻔한 해석 뒤집기: "다들 ~라고 하는데, 반전은 ~야"
  · 도발적인 질문: "근데 이거 진짜 ~일까?", "그럼 ~는 어떻게 되는 거야?"
  · 악마의 변호인: 일부러 반대편 입장에서 한 번 찔러보기
  · 엉뚱하지만 정확한 비유나 말장난, 과장된 리액션("이게 되네?", "우연? 아니지ㅋㅋ")
  · 남들이 못 본 연결고리: 다른 소식이나 흐름과 엮어서 "그러니까 이거랑 그거 같은 얘기야"
- 사실은 정확히 지키고, 없는 내용을 지어내지 않습니다. 사고·피해 소식의 피해자는
  조롱하지 않습니다(비꼬는 대상은 회사·제도·상황).
- 코멘트 문장도 짧게 씁니다.

[논리 점검] 다 쓴 뒤 기사마다 스스로 확인합니다:
  · 주어와 대상이 정확한가 (누가 → 누구에게 → 무엇을). 인물·회사 이름을 바꾸거나 빼지 않았는가.
  · "앞뒤가 안 맞는다", "아이러니"라고 쓸 때 무엇과 무엇이 부딪히는지 양쪽을 적었는가.
  · 발언은 누가, 어떤 자리에서, 무슨 질문에 답하며 한 말인지 적었는가.
  · 이전 브리핑 소식을 다시 언급할 때 원래 내용과 다르게 줄여 쓰지 않았는가.
  · 40자 넘는 문장, 번역투, 중학생이 멈칫할 단어가 남지 않았는가. 남았으면 고칩니다.

[body - 전체 브리핑 페이지용, 기사마다]
- 페이지는 길어도 괜찮습니다(텔레그램은 요약, 페이지는 자세히). 5개 기사 모두 아래 분량으로 씁니다.
- 네 부분으로 나누고, 각 부분은 표시어로 시작합니다. 한 부분 안에서도 내용 덩어리마다
  줄바꿈으로 나눠 읽기 쉽게 합니다(표시어는 각 부분의 첫 줄에만).
  "📌 무슨 일? " → 짧은 문장 10~14개. 언제·누가·무엇을 → 구체적으로 어떻게 일어났는지 →
    관련된 다른 회사·사람·수치 → 왜 그런 의심·평가가 나왔는지(근거) → 아직 확인 안 된 것 →
    정부·회사의 대응. 후속 소식이면 이전에 무슨 일이 있었고 이번에 뭐가 새로운지부터.
  "🧭 배경 " → 이 기사 이해에 꼭 필요한 배경 3~5문장. 필요 없으면 이 부분은 뺍니다.
  "💡 쉽게 말하면 " → 일상 비유 + 이게 왜 중요한지, 나(독자)한테 무슨 의미인지 5~7문장.
  "💬 ENTP 한마디 " → 위 ENTP 규칙대로 5~7문장.
- 좋은 예 (이 모양과 분량을 따르세요. 실제 내용은 그날 기사로 씁니다):
📌 무슨 일? 지난 6일, 이재명 대통령이 국무회의에서 "일부 은행 해킹에 AI가 쓰인 징후가 나타났다"고 말했어.
사건은 9월 29일 밤부터 30일 새벽 사이에 일어났어. 해커가 본인 확인 절차를 우회해서 신한은행의 대출 영업용 조회 서비스에 몰래 들어왔어. 그렇게 고객 약 2만5000명의 개인정보와 신용정보가 빠져나갔어.
KB국민은행(119명)과 하나은행(89명)에서도 정보가 샜어. 부산은행, 현대캐피탈, 예가람저축은행도 공격을 받거나 뚫렸어. 반면 우리은행과 NH농협은행은 아직 유출이 확인되지 않았어.
AI 얘기가 나온 건 공격 서버에서 'AI 자율 침투 도구'로 보이는 흔적이 나와서야. 사람 대신 AI가 알아서 약점을 찾아 들어가는 프로그램이야. 다만 어떤 AI가 쓰였는지는 아직 공식 발표가 없어.
경찰은 조사에 들어갔고, 대통령은 정부 전체가 보안 대책을 세우라고 지시했어.
🧭 배경 보통 해커는 약한 곳을 직접 하나하나 찔러 봐야 해. 시간도 오래 걸리고 실력 있는 사람이 붙어 있어야 하지. 그런데 요즘 AI는 코드를 읽고, 약한 곳을 찾고, 시험해 보는 걸 혼자 할 수 있어. 그래서 보안 전문가들은 "해킹이 훨씬 싸고 빨라질 것"이라고 경고해 왔어. 이번 사건은 그 걱정이 한국 은행에서 실제로 나타났을 수 있다는 첫 신호야.
💡 쉽게 말하면 원래 도둑은 동네 집 창문을 하나씩 흔들어 보며 다녔어. 이번엔 로봇이 "이 집 창문이 약해"라고 미리 골라 준 셈이야. 그러면 도둑 한 명이 하룻밤에 털 수 있는 집이 확 늘어나. 그런데 창문을 잘 잠근 집(우리·농협은행)은 로봇이 와도 못 들어갔어. 내 정보를 맡긴 은행의 보안 실력이 이제 진짜 중요해졌다는 뜻이야. 그리고 "본인 인증" 같은 귀찮은 절차가 사실 내 정보를 지키는 문이라는 뜻이기도 해.
💬 ENTP 한마디 다들 "AI가 은행을 털었다!"에 놀라는데, 반전은 따로 있어. AI는 문을 부순 게 아니라 이미 열려 있던 문을 찾아냈을 뿐이야. 같은 공격을 받고도 어떤 은행은 2만5000명이 털리고, 어떤 은행은 0명이었잖아. 그럼 진짜 질문은 이거지. 이번 사고, AI 탓이야, 아니면 문단속 안 한 은행 탓이야? 그리고 AI는 지키는 쪽도 똑같이 쓸 수 있어. 결국 "누가 먼저 AI로 약한 창문을 찾느냐" 달리기가 시작된 거야. 이게 되네? 가 아니라, 이러면 안 되는데 되네ㅋㅋ

[one_liner]
- 그날 소식 전체를 묶는 한 문장. 짧은 ENTP 반말로, 툭 던지는 느낌.

[message_text - 텔레그램용]
- 700~1300자. 이모지는 기사 표시 외에 1~3개만.
- 형식:
  첫 줄: 오늘 분위기를 한 방에 요약하는 ENTP 한 문장
  (빈 줄)
  기사마다:
    "• [10/6] " + 무슨 일인지 짧은 문장 2~3개 (후속이면 "• [10/6·후속] "으로 시작하고 새 내용부터)
    "💬 " + ENTP 코멘트 1~2문장 (위 ENTP 규칙대로, 반드시 성격이 드러나게)
  (기사 사이 빈 줄)
  마지막: "결론: " + 생각할 거리를 던지는 ENTP 한두 문장.
- 처음 듣는 사람도 이 메시지만 읽고 무슨 일인지 알 수 있어야 합니다.
- 기사 제목을 그대로 옮기지 마세요. 마크다운 문법, 링크, 버튼 문구는 넣지 마세요
  (버튼은 별도로 붙습니다).
"""


def _recent_briefings(today: str, days: int = RECENT_DAYS) -> list[dict]:
    """오늘 이전 최근 며칠 치 브리핑의 기사 제목 (중복 판단용)."""
    recent = []
    for f in sorted(DATA_DIR.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].json"), reverse=True):
        if f.stem >= today:
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        recent.append({
            "briefing_date": f.stem,
            "articles": [
                {"title": a["title"], "event_date": a.get("event_date")} for a in d.get("articles", [])
            ],
        })
        if len(recent) >= days:
            break
    return recent


def _build_user_prompt(candidates: list, needs_search: list[dict], rankings: list[dict]) -> str:
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
        f"주요 언론사 배치 순위 (중요도 판단 기준):\n"
        f"{json.dumps(rankings, ensure_ascii=False, indent=2)}\n\n"
        f"최근 브리핑에서 이미 다룬 소식 (중복 판단용):\n"
        f"{json.dumps(_recent_briefings(today_kst), ensure_ascii=False, indent=2)}\n\n"
        "위 규칙에 따라 선별하고 작성하세요."
    )


def select_and_write(candidates: list, needs_search: list[dict], rankings: list[dict]) -> dict:
    today_kst = datetime.now(KST).strftime("%Y-%m-%d")
    user_prompt = _build_user_prompt(candidates, needs_search, rankings)

    envelope = run_claude(
        prompt=user_prompt,
        system_prompt=SYSTEM_PROMPT,
        allowed_tools="WebSearch",
        json_schema=JSON_SCHEMA,
        timeout=1200,  # 기사 5개를 길게 쓰므로 기본 10분보다 넉넉히
    )

    data = envelope.get("structured_output")
    if not data:
        raise RuntimeError(f"Claude 응답에 structured_output이 없습니다: {envelope.get('result')}")

    if len(data.get("message_text", "")) > MESSAGE_LIMIT:
        print(
            f"[select_and_write] 경고: message_text가 {len(data['message_text'])}자로 "
            f"{MESSAGE_LIMIT}자를 초과했습니다. 잘라냅니다.",
            file=sys.stderr,
        )
        data["message_text"] = data["message_text"][:MESSAGE_LIMIT]

    data.setdefault("date", today_kst)
    for i, art in enumerate(data.get("articles", []), start=1):
        art.setdefault("rank", i)

    return data


if __name__ == "__main__":
    from collect import collect_all
    from rankings import collect_rankings

    cands, missing = collect_all()
    result = select_and_write(cands, missing, collect_rankings())
    print(json.dumps(result, ensure_ascii=False, indent=2))
