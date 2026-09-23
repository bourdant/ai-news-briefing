# AI 뉴스 브리핑 자동화

매일 14:00 KST에 AI 뉴스를 모아 Claude Code(구독 기반)로 선별·작성하고, GitHub Pages에
올린 뒤 카카오톡 "나에게 보내기"로 요약 + 링크를 보냅니다. 2주마다 🔥 반응을 분석해
카카오톡으로 요약해 줍니다.

## 구성

- `pipeline/` — 수집(RSS) → 선별/작성(Claude Code CLI) → 렌더링 → 카카오톡 전송 파이썬 스크립트
- `pipeline/claude_cli.py` — Claude Code CLI를 헤드리스로 호출하는 공통 헬퍼 (API 과금 대신
  Claude Pro/Max 구독의 `CLAUDE_CODE_OAUTH_TOKEN` 사용)
- `docs/` — GitHub Pages로 서빙되는 정적 사이트 (자동 생성됨)
- `cloudflare-worker/` — 반응 버튼(🔥/😐/💤) 클릭을 기록하는 Cloudflare Worker + KV
- `.github/workflows/`
  - `daily-briefing.yml` — 매일 05:00 UTC(14:00 KST) 전체 파이프라인 실행
  - `biweekly-analysis.yml` — 매주 월요일 체크, 실제로는 14일 간격으로만 분석 전송
  - `deploy-worker.yml` — `cloudflare-worker/` 변경 시 Worker 자동 배포

## 필요한 GitHub Secrets

| 이름 | 용도 |
|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | Claude Pro/Max 구독 기반 장기 토큰 (`claude setup-token`으로 발급, 1년 유효, 만료 전 재발급 필요) — Claude 호출(선별/작성, 웹 검색, 2주 분석 요약)에 사용, 별도 API 과금 없음 |
| `KAKAO_REST_API_KEY` | 카카오 앱 REST API 키 |
| `KAKAO_REFRESH_TOKEN` | 카카오 "나에게 보내기" 권한의 refresh_token |
| `KAKAO_CLIENT_SECRET` | (선택) 카카오 앱에서 Client Secret을 켠 경우만 |
| `GH_PAT` | refresh_token이 회전될 때 이 Secret을 자동 갱신하기 위한 개인 액세스 토큰 (repo 권한) |
| `ANALYSIS_API_KEY` | Worker `/analysis` 엔드포인트 보호용 공유 키 (Worker secret과 동일 값) |

## 필요한 GitHub Actions Variables (Settings → Secrets and variables → Actions → Variables)

| 이름 | 예시 |
|---|---|
| `PAGE_BASE_URL` | `https://username.github.io/ai-news-briefing` |
| `CF_WORKER_URL` | `https://ai-news-reactions.username.workers.dev` |

## 로컬에서 한 번 해야 하는 일

0. Claude Code CLI 설치 후 `claude setup-token`으로 구독 기반 토큰 발급 (브라우저 로그인 필요,
   1년마다 재발급) → `CLAUDE_CODE_OAUTH_TOKEN` Secret에 등록
1. `pip install -r requirements.txt`
2. 카카오 인가 코드 발급 후: `KAKAO_REST_API_KEY=... python pipeline/kakao_bootstrap.py <REDIRECT_URI> <CODE>` 로 refresh_token 발급
3. Cloudflare Worker 배포: `cd cloudflare-worker && npx wrangler kv namespace create REACTIONS` → `wrangler.toml`에 id 채우기 → `npx wrangler secret put ANALYSIS_API_KEY` → `npx wrangler deploy`

## 수동 실행 (테스트)

- GitHub 저장소 → Actions → "Daily AI News Briefing" → Run workflow
- 카카오톡 연동만 테스트: `python pipeline/send_kakao.py --test`

## 참고

- GitHub Actions cron은 부하에 따라 최대 수~수십 분 지연될 수 있습니다.
- 모든 API 키/토큰은 GitHub Secrets에만 저장되며 저장소 코드에는 포함되지 않습니다.
