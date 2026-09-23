"""Claude Pro/Max 구독의 Claude Code CLI를 헤드리스로 호출하는 공통 헬퍼.

API 과금(ANTHROPIC_API_KEY) 대신, 구독 기반 장기 토큰(CLAUDE_CODE_OAUTH_TOKEN,
`claude setup-token`으로 1회 발급)을 사용해 GitHub Actions에서 호출한다.
"""
from __future__ import annotations

import json
import os
import subprocess

DEFAULT_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")


def run_claude(
    prompt: str,
    system_prompt: str | None = None,
    allowed_tools: str = "",
    json_schema: dict | None = None,
    model: str | None = None,
    timeout: int = 600,
) -> dict:
    """Claude Code CLI를 헤드리스(-p)로 호출하고 결과 envelope(dict)를 반환한다.

    json_schema를 넘기면 envelope["structured_output"]에 스키마에 맞는 파싱된
    결과가 담긴다. 넘기지 않으면 envelope["result"]가 순수 텍스트다.
    """
    if "CLAUDE_CODE_OAUTH_TOKEN" not in os.environ:
        raise RuntimeError(
            "CLAUDE_CODE_OAUTH_TOKEN 환경변수가 없습니다. "
            "GitHub Secret에 구독 기반 토큰이 등록돼 있는지 확인하세요."
        )

    cmd = [
        "claude", "-p", prompt,
        "--output-format", "json",
        "--permission-prompts", "none",
        "--model", model or DEFAULT_MODEL,
    ]
    if system_prompt:
        cmd += ["--append-system-prompt", system_prompt]
    if allowed_tools:
        cmd += ["--allowedTools", allowed_tools]
    if json_schema:
        cmd += ["--json-schema", json.dumps(json_schema, ensure_ascii=False)]

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Claude Code CLI 실행 실패 (exit {proc.returncode}): {proc.stderr[:2000]}"
        )

    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Claude Code CLI 출력이 JSON이 아닙니다: {proc.stdout[:2000]}") from exc

    if envelope.get("is_error"):
        raise RuntimeError(f"Claude Code 실행 오류: {envelope}")

    return envelope
