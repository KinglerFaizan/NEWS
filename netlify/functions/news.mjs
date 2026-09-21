const CATEGORIES = {
  "Transformation": [
    'bank AND ("digital transformation" OR "core banking")',
    'banking AND ("artificial intelligence" OR cloud OR automation)'
  ],
  "Regulation": [
    'bank AND (regulation OR compliance OR supervision)',
    'RBI AND (penalty OR guidelines OR circular)',
    'bank AND ("money laundering" OR AML OR KYC OR fraud)'
  ],
  "People": [
    'bank AND ("chief risk officer" OR "audit committee")',
    'bank AND (appointed OR resigns OR board)'
  ],
  "Global Banks": [
    'HSBC OR JPMorgan OR Citigroup OR Barclays',
    'UBS OR "Deutsche Bank" OR "Goldman Sachs" OR "Standard Chartered"'
  ]
};

const API_URL = "https://newsdata.io/api/1/news";
const CACHE_MS = 5 * 60 * 1000;
let cache = { at: 0, data: null };

function clean(value) {
  return value == null ? "" : String(value).trim();
}

function canonicalUrl(url) {
  try {
    const u = new URL(clean(url));
    u.hostname = u.hostname.replace(/^www\./, "").toLowerCase();
    for (const key of [...u.searchParams.keys()]) {
      if (/^(utm_|fbclid|gclid|mc_|ref|cmpid|icid)/i.test(key)) u.searchParams.delete(key);
    }
    u.hash = "";
    return u.toString().replace(/\/$/, "").toLowerCase();
  } catch {
    return clean(url).toLowerCase();
  }
}

function normalizeTitle(title) {
  return clean(title)
    .toLowerCase()
    .replace(/\s+[-|—–]\s+[^-|—–]{1,60}$/, "")
    .replace(/[^a-z0-9 ]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function tokenSet(title) {
  const stop = new Set(["the","a","an","and","or","of","to","in","on","for","with","at","by","from","as","is","are","was","were","be","been","it","its","that","this","these","those","after","over","amid","says","say","new","news","report","reports","update","updates","live"]);
  return new Set(normalizeTitle(title).split(" ").filter(w => w.length > 2 && !stop.has(w)));
}

function similarity(a, b) {
  const A = tokenSet(a), B = tokenSet(b);
  if (!A.size || !B.size) return 0;
  let intersection = 0;
  for (const x of A) if (B.has(x)) intersection++;
  return intersection / Math.min(A.size, B.size);
}

function dedupe(rows) {
  const seenUrl = new Set();
  const seenTitle = new Set();
  const result = [];

  for (const row of rows) {
    const url = canonicalUrl(row.url);
    const title = normalizeTitle(row.title);
    if (!title || title.startsWith("[removed]")) continue;
    if (url && seenUrl.has(url)) continue;
    if (title && seenTitle.has(title)) continue;

    let duplicate = false;
    for (const existing of result) {
      if (similarity(title, existing.title) >= 0.86) {
        duplicate = true;
        break;
      }
    }
    if (duplicate) continue;

    result.push(row);
    if (url) seenUrl.add(url);
    if (title) seenTitle.add(title);
  }
  return result;
}

function normalizeArticle(article, category) {
  return {
    id: category + "-" + clean(article.article_id || article.link || article.title),
    category,
    title: clean(article.title) || "Untitled story",
    description: clean(article.description) || "Independent institutional briefing coverage.",
    url: clean(article.link),
    image: clean(article.image_url),
    source: clean(article.source_name || article.source_id || "NewsData"),
    publishedAt: clean(article.pubDate),
    creator: Array.isArray(article.creator) ? article.creator.join(", ") : clean(article.creator)
  };
}

async function fetchCategory(category, queries, apiKey) {
  const rows = [];
  for (const q of queries) {
    const params = new URLSearchParams({
      apikey: apiKey,
      q: q.slice(0, 100),
      language: "en",
      category: "business,technology,world,politics"
    });
    const response = await fetch(API_URL + "?" + params.toString());
    const payload = await response.json().catch(() => ({}));

    if (!response.ok || payload.status !== "success") {
      const message = payload?.results?.message || payload?.message || ("HTTP " + response.status);
      throw new Error(message);
    }

    for (const article of payload.results || []) {
      rows.push(normalizeArticle(article, category));
    }
  }
  return rows;
}

export default async () => {
  const apiKey = clean(Netlify.env.get("NEWSDATA_API_KEY"));
  if (!apiKey) {
    return new Response(JSON.stringify({
      ok: false,
      error: "NEWSDATA_API_KEY is not configured in Netlify environment variables."
    }), {
      status: 500,
      headers: { "content-type": "application/json", "cache-control": "no-store" }
    });
  }

  if (cache.data && Date.now() - cache.at < CACHE_MS) {
    return new Response(JSON.stringify({ ok: true, ...cache.data, cached: true }), {
      headers: { "content-type": "application/json", "cache-control": "public, max-age=300" }
    });
  }

  try {
    const settled = await Promise.all(
      Object.entries(CATEGORIES).map(async ([category, queries]) => {
        const articles = await fetchCategory(category, queries, apiKey);
        return [category, articles];
      })
    );

    const all = dedupe(settled.flatMap(([, articles]) => articles))
      .sort((a, b) => new Date(b.publishedAt || 0) - new Date(a.publishedAt || 0));

    const counts = Object.fromEntries(Object.keys(CATEGORIES).map(category => [
      category,
      all.filter(a => a.category === category).length
    ]));

    const data = {
      fetchedAt: new Date().toISOString(),
      total: all.length,
      sources: new Set(all.map(a => a.source).filter(Boolean)).size,
      categories: Object.keys(CATEGORIES),
      counts,
      articles: all
    };

    cache = { at: Date.now(), data };
    return new Response(JSON.stringify({ ok: true, ...data, cached: false }), {
      headers: {
        "content-type": "application/json",
        "cache-control": "public, max-age=300, stale-while-revalidate=600"
      }
    });
  } catch (error) {
    return new Response(JSON.stringify({
      ok: false,
      error: clean(error?.message) || "Unable to fetch current news."
    }), {
      status: 502,
      headers: { "content-type": "application/json", "cache-control": "no-store" }
    });
  }
};
