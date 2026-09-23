/**
 * AI 뉴스 브리핑 반응(🔥/😐/💤) 기록용 Cloudflare Worker.
 *
 * 라우트:
 *   POST /react            body {date, id, reaction} -> 카운트 +1, 최신 카운트 반환
 *   GET  /counts?date&id   -> 해당 기사 카운트 {fire, meh, sleep}
 *   GET  /analysis?since&until (X-Api-Key 헤더 필요)
 *                           -> since~until 사이 모든 반응 원본 목록 (2주 분석용)
 *
 * KV 바인딩: REACTIONS
 * 환경변수: PAGES_ORIGIN (CORS 허용 origin, 예: https://username.github.io)
 * 시크릿:   ANALYSIS_API_KEY (wrangler secret put 로 설정, /analysis 보호용)
 */

const REACTIONS = ["fire", "meh", "sleep"];

function corsHeaders(env) {
  return {
    "Access-Control-Allow-Origin": env.PAGES_ORIGIN || "*",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type,X-Api-Key",
  };
}

function json(data, env, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", ...corsHeaders(env) },
  });
}

function isValidDate(d) {
  return typeof d === "string" && /^\d{4}-\d{2}-\d{2}$/.test(d);
}

function isValidId(id) {
  return typeof id === "string" && /^[a-z0-9-]{1,120}$/.test(id);
}

async function getCounts(env, date, id) {
  const values = await Promise.all(
    REACTIONS.map((r) => env.REACTIONS.get(`r:${date}:${id}:${r}`))
  );
  const counts = {};
  REACTIONS.forEach((r, i) => {
    counts[r] = parseInt(values[i] || "0", 10);
  });
  return counts;
}

async function handleReact(request, env) {
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "invalid json" }, env, 400);
  }
  const { date, id, reaction } = body || {};
  if (!isValidDate(date) || !isValidId(id) || !REACTIONS.includes(reaction)) {
    return json({ error: "invalid params" }, env, 400);
  }

  const key = `r:${date}:${id}:${reaction}`;
  const current = parseInt((await env.REACTIONS.get(key)) || "0", 10);
  await env.REACTIONS.put(key, String(current + 1));

  // 날짜별 기사 id 인덱스를 함께 관리 (2주 분석에서 사용)
  const indexKey = `idx:${date}`;
  const idxRaw = await env.REACTIONS.get(indexKey);
  const ids = idxRaw ? JSON.parse(idxRaw) : [];
  if (!ids.includes(id)) {
    ids.push(id);
    await env.REACTIONS.put(indexKey, JSON.stringify(ids));
  }

  const counts = await getCounts(env, date, id);
  return json({ ok: true, counts }, env);
}

async function handleCounts(request, env) {
  const url = new URL(request.url);
  const date = url.searchParams.get("date");
  const id = url.searchParams.get("id");
  if (!isValidDate(date) || !isValidId(id)) {
    return json({ error: "invalid params" }, env, 400);
  }
  const counts = await getCounts(env, date, id);
  return json({ counts }, env);
}

function dateRange(since, until) {
  const dates = [];
  let d = new Date(since + "T00:00:00Z");
  const end = new Date(until + "T00:00:00Z");
  while (d <= end) {
    dates.push(d.toISOString().slice(0, 10));
    d = new Date(d.getTime() + 86400000);
  }
  return dates;
}

async function handleAnalysis(request, env) {
  const apiKey = request.headers.get("X-Api-Key");
  if (!env.ANALYSIS_API_KEY || apiKey !== env.ANALYSIS_API_KEY) {
    return json({ error: "unauthorized" }, env, 401);
  }
  const url = new URL(request.url);
  const since = url.searchParams.get("since");
  const until = url.searchParams.get("until") || new Date().toISOString().slice(0, 10);
  if (!isValidDate(since) || !isValidDate(until)) {
    return json({ error: "invalid params" }, env, 400);
  }

  const rows = [];
  for (const date of dateRange(since, until)) {
    const idxRaw = await env.REACTIONS.get(`idx:${date}`);
    if (!idxRaw) continue;
    const ids = JSON.parse(idxRaw);
    for (const id of ids) {
      const counts = await getCounts(env, date, id);
      rows.push({ date, id, counts });
    }
  }
  return json({ since, until, rows }, env);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders(env) });
    }

    if (url.pathname === "/react" && request.method === "POST") {
      return handleReact(request, env);
    }
    if (url.pathname === "/counts" && request.method === "GET") {
      return handleCounts(request, env);
    }
    if (url.pathname === "/analysis" && request.method === "GET") {
      return handleAnalysis(request, env);
    }
    return json({ error: "not found" }, env, 404);
  },
};
