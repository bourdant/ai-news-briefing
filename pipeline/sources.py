"""AI 뉴스 브리핑 소스 목록.

kind:
  official_blog - 회사 공식 블로그 (신규 모델/기능 발표는 무조건 포함 대상)
  aggregator    - Techmeme 등 뉴스 취합 사이트
  community     - Hacker News, GeekNews 등 커뮤니티
  newsletter    - The Rundown AI, TLDR AI, The Batch 등 뉴스레터형 사이트
  media         - AI타임스 등 언론사

rss가 None이면 collect.py가 RSS 수집을 건너뛰고, select_and_write.py가
Claude 웹 검색으로 그 소스를 보완 조회하도록 needs_search=True로 표시한다.
RSS가 있어도 그날 실행 시 실패(파싱 오류·404 등)하면 동일하게 웹 검색 보완 대상이 된다.
"""

SOURCES = [
    {
        "key": "techmeme",
        "name": "Techmeme",
        "rss": "https://www.techmeme.com/feed.xml",
        "kind": "aggregator",
        "needs_search": False,
    },
    {
        "key": "hackernews",
        "name": "Hacker News",
        "rss": "https://hnrss.org/newest?points=80",
        "kind": "community",
        "needs_search": False,
        # HN 피드는 AI 주제로 한정되어 있지 않으므로 collect.py에서 키워드 필터링한다.
        "keyword_filter": True,
    },
    {
        "key": "geeknews",
        "name": "GeekNews",
        "rss": "https://feeds.feedburner.com/geeknews-feed",
        "kind": "community",
        "needs_search": False,
    },
    {
        "key": "rundown",
        "name": "The Rundown AI",
        "rss": None,
        "homepage": "https://www.therundown.ai",
        "kind": "newsletter",
        "needs_search": True,
    },
    {
        "key": "tldr_ai",
        "name": "TLDR AI",
        "rss": "https://tldr.tech/api/rss/ai",
        "kind": "newsletter",
        "needs_search": False,
    },
    {
        "key": "the_batch",
        "name": "The Batch",
        "rss": "https://www.deeplearning.ai/the-batch/feed/",
        "kind": "newsletter",
        "needs_search": False,
    },
    {
        "key": "openai_blog",
        "name": "OpenAI 공식 블로그",
        "rss": "https://openai.com/news/rss.xml",
        "kind": "official_blog",
        "needs_search": False,
    },
    {
        "key": "anthropic_blog",
        "name": "Anthropic 공식 블로그",
        "rss": None,
        "homepage": "https://www.anthropic.com/news",
        "kind": "official_blog",
        "needs_search": True,
    },
    {
        "key": "deepmind_blog",
        "name": "Google DeepMind 공식 블로그",
        "rss": "https://deepmind.google/blog/rss.xml",
        "kind": "official_blog",
        "needs_search": False,
    },
    {
        "key": "aitimes",
        "name": "AI타임스",
        "rss": "https://www.aitimes.com/rss/allArticle.xml",
        "kind": "media",
        "needs_search": False,
    },
]

AI_KEYWORDS = [
    "ai", "artificial intelligence", "llm", "gpt", "openai", "anthropic",
    "claude", "gemini", "deepmind", "chatgpt", "genai", "generative ai",
    "machine learning", "neural network", "transformer", "agentic",
    "인공지능", "생성형", "챗gpt", "오픈ai", "앤트로픽", "제미나이", "딥마인드",
]
