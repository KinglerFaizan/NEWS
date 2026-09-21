"""Audit Intelligence — futuristic Streamlit executive newsroom."""
import os
from collections import Counter
from datetime import datetime, timezone
from html import escape

import pandas as pd
import streamlit as st
import news_providers as npv

st.set_page_config(page_title="Audit Intelligence", page_icon="◈", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');
:root{--bg:#07120f;--panel:#0d1d18;--line:rgba(218,255,239,.11);--ink:#f2faf6;--muted:#8fa79f;--acid:#c7ff4a;--mint:#76f7c5;--cyan:#70d8ff}
.stApp{background:radial-gradient(800px 420px at 80% -10%,rgba(95,170,130,.13),transparent 62%),var(--bg);color:var(--ink);font-family:'DM Sans',sans-serif}
[data-testid="stHeader"]{background:transparent} footer,#MainMenu{visibility:hidden}.block-container{max-width:1500px;padding:28px 42px 55px}
.ai-head{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);padding:6px 0 22px}
.brand{display:flex;gap:14px;align-items:center}.mark{width:48px;height:48px;border:1px solid rgba(199,255,74,.35);border-radius:14px;display:grid;place-items:center;background:#0d2119;box-shadow:0 0 25px rgba(199,255,74,.07)}
.brand-name{font:700 22px 'Space Grotesk';letter-spacing:-.6px}.brand-sub,.status{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:1.7px;margin-top:3px}.status{display:flex;align-items:center;gap:8px;color:#b6cbc3}.dot{width:7px;height:7px;background:var(--acid);border-radius:50%;box-shadow:0 0 14px var(--acid)}
.hero{position:relative;overflow:hidden;margin:24px 0 15px;padding:34px 38px;border:1px solid rgba(218,255,239,.15);border-radius:22px;background:linear-gradient(135deg,#0d241c,#08140f);box-shadow:0 25px 65px rgba(0,0,0,.22)}
.hero:after{content:"";position:absolute;inset:0;pointer-events:none;background-image:linear-gradient(rgba(199,255,74,.025) 1px,transparent 1px),linear-gradient(90deg,rgba(199,255,74,.025) 1px,transparent 1px);background-size:34px 34px}
.kicker{position:relative;color:var(--acid);font-size:9px;font-weight:700;letter-spacing:2px;text-transform:uppercase}.title{position:relative;margin-top:10px;max-width:900px;font:600 clamp(36px,5vw,64px)/.98 'Space Grotesk';letter-spacing:-3px}.title span{color:var(--acid)}.copy{position:relative;max-width:700px;color:#a7bbb3;font-size:12px;line-height:1.65;margin-top:14px}.chips{position:relative;display:flex;flex-wrap:wrap;gap:8px;margin-top:21px}.chip{padding:7px 10px;border:1px solid var(--line);border-radius:999px;color:#b5c8c0;font-size:9px;letter-spacing:.8px;text-transform:uppercase}.chip b{color:var(--ink)}
.news-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.section{margin:28px 0 12px;display:flex;justify-content:space-between;align-items:end}.section-title{font:600 18px 'Space Grotesk';display:flex;gap:10px;align-items:center}.section-title:before{content:"";width:3px;height:21px;background:var(--acid);border-radius:3px;box-shadow:0 0 12px rgba(199,255,74,.25)}.count{font:10px 'Space Grotesk';color:#627a71;text-transform:uppercase;letter-spacing:1px}
.card{min-width:0;display:grid;grid-template-columns:150px 1fr;gap:15px;padding:10px;border:1px solid var(--line);border-radius:15px;background:linear-gradient(145deg,#10231c,#0a1814);transition:.18s}.card:hover{transform:translateY(-2px);border-color:rgba(199,255,74,.28);box-shadow:0 16px 34px rgba(0,0,0,.23)}.thumb{height:130px;overflow:hidden;border-radius:10px;background:#12251e}.thumb img{width:100%;height:100%;object-fit:cover;display:block;filter:saturate(.82);transition:.3s}.card:hover .thumb img{transform:scale(1.04)}.body{min-width:0;display:flex;flex-direction:column}.meta{display:flex;justify-content:space-between;gap:8px;color:#607970;font-size:8px;text-transform:uppercase;letter-spacing:.9px}.tag{color:#d2e4dc}.headline{font:600 16px/1.25 'Space Grotesk';letter-spacing:-.3px;margin:8px 0 6px}.headline a{color:var(--ink);text-decoration:none}.headline a:hover{color:var(--acid)}.desc{color:#819a91;font-size:10.5px;line-height:1.45;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.foot{display:flex;justify-content:space-between;gap:8px;margin-top:auto;padding-top:9px}.source{color:#a7bbb3;font-size:8.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.read{color:var(--acid);font-size:8.5px;font-weight:800;text-decoration:none;text-transform:uppercase;letter-spacing:.8px}
.rail{border:1px solid var(--line);border-radius:15px;background:rgba(13,29,24,.8);padding:16px;margin-bottom:12px}.rail-title{font-size:9px;font-weight:700;color:#d8e8e2;text-transform:uppercase;letter-spacing:1.3px;margin-bottom:10px}.row{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid rgba(218,255,239,.06);font-size:10px}.row:last-child{border-bottom:0}.row span:first-child{color:#7e978e}.row b{font:700 12px 'Space Grotesk';color:#e4f1ec}.bar{height:4px;background:#193027;border-radius:5px;overflow:hidden;margin-top:4px}.fill{height:100%;background:linear-gradient(90deg,var(--mint),var(--acid))}
[data-testid="stTextInput"] input{background:#0a1814!important;border:1px solid var(--line)!important;color:var(--ink)!important;border-radius:10px!important}[data-testid="stTextInput"] input:focus{border-color:rgba(199,255,74,.5)!important;box-shadow:0 0 0 2px rgba(199,255,74,.07)!important}
.stButton>button{background:var(--acid)!important;color:#07120f!important;border:0!important;border-radius:10px!important;font-weight:800!important;min-height:40px}.stButton>button:hover{box-shadow:0 0 20px rgba(199,255,74,.14)}
[data-testid="stExpander"]{background:#0a1814!important;border:1px solid var(--line)!important;border-radius:12px!important}.app-foot{margin-top:34px;padding-top:18px;border-top:1px solid var(--line);display:flex;justify-content:space-between;color:#607970;font-size:8px;text-transform:uppercase;letter-spacing:1px}
@media(max-width:1100px){.news-grid{grid-template-columns:1fr}.card{grid-template-columns:180px 1fr}}@media(max-width:700px){.block-container{padding:18px 15px 40px}.status{display:none}.hero{padding:26px 22px}.title{font-size:40px;letter-spacing:-2px}.card{grid-template-columns:1fr}.thumb{height:180px}.app-foot{display:block;line-height:2}}
</style>
""", unsafe_allow_html=True)

CATEGORIES=["Transformation","Regulation","People","Global Banks"]
CATEGORY_COLORS={"Transformation":"#70D8FF","Regulation":"#C7FF4A","People":"#B7A7FF","Global Banks":"#76F7C5"}
TERMS={
"Transformation":["digital transformation","modernization","modernisation","core banking","automation","artificial intelligence","generative ai","genai","machine learning","cloud","digital banking","technology transformation"],
"Regulation":["regulation","regulatory","rbi","basel","prudential","supervision","supervisory","enforcement","aml","anti-money laundering","kyc","sanctions","capital requirements","compliance"],
"People":["appointed","appointment","ceo","cfo","cro","ciso","chief audit","internal audit","audit committee","board","director","chairman","leadership","executive"],
"Global Banks":["hsbc","jpmorgan","jpmorgan chase","citi","citigroup","barclays","deutsche bank","ubs","bnp paribas","santander","standard chartered","bank of america","goldman sachs","morgan stanley","wells fargo","ing","icbc","mufg","mizuho"]}
AUDIT_TERMS=["audit","internal control","control weakness","governance","risk management","operational risk","model risk","compliance","regulatory","supervision","enforcement","aml","kyc","sanctions","fraud","misconduct","financial crime","bank","banking","rbi","basel","credit risk","liquidity","penalty","fined","investigation","whistleblower","irregularities","lapses","cybersecurity","ransomware","data breach"]
ALERT_TERMS=["enforcement","penalty","fined","fine","fraud","misconduct","investigation","probe","money laundering","aml","sanctions","irregularities","lapses","control deficiency","restatement","whistleblower"]

def key():
    value=os.getenv("NEWSDATA_API_KEY") or os.getenv("NEWSDATA_KEY")
    if not value:
        try: value=st.secrets.get("NEWSDATA_API_KEY") or st.secrets.get("NEWSDATA_KEY")
        except Exception: value=""
    return str(value or "").strip()

def classify(title,desc,hint):
    if hint in CATEGORIES:return hint
    text=f"{title} {desc}".lower()
    scores={c:sum(text.count(t) for t in terms) for c,terms in TERMS.items()}
    return max(scores,key=scores.get) if max(scores.values(),default=0) else "Transformation"

def relevance(title,desc):
    text=f"{title} {desc}".lower()
    return min(40,sum(2 if " " in t else 1 for t in AUDIT_TERMS if t in text))

def ago(value):
    try:
        dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
        mins=max(0,int((datetime.now(timezone.utc)-dt.astimezone(timezone.utc)).total_seconds()/60))
        return f"{mins}m ago" if mins<60 else f"{mins//60}h ago" if mins<1440 else f"{mins//1440}d ago"
    except Exception:return "Recent"

@st.cache_data(ttl=300,show_spinner=False)
def load_news(api_key,days,min_rel,cats):
    raw,errors,stats=npv.fetch_all({"newsdata":api_key},lookback_days=days,categories=list(cats),fuzzy_threshold=.72,max_workers=6)
    rows=[]
    for r in raw:
        title=str(r.get("title") or "").strip()
        if not title:continue
        desc=str(r.get("description") or r.get("content") or "").strip()
        score=relevance(title,desc)
        cat=classify(title,desc,r.get("category_hint"))
        if cat not in cats or score<min_rel:continue
        rows.append({"title":title,"description":desc,"url":str(r.get("url") or "#"),"image_url":str(r.get("image_url") or ""),"source":str(r.get("source") or "Unknown"),"publishedAt":r.get("published_at") or "","category":cat,"score":score})
    rows.sort(key=lambda x:(x["score"],x["publishedAt"]),reverse=True)
    stats=dict(stats or {});stats["kept"]=len(rows)
    return rows,errors,stats

def img_fallback(color):
    return f"data:image/svg+xml;charset=utf-8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 600 340'><rect width='600' height='340' fill='%230f241d'/><circle cx='470' cy='90' r='65' fill='{color}' opacity='.1'/><path d='M0 285L180 170l100 65 110-105 210 130v80H0z' fill='{color}' opacity='.1'/></svg>"

def cards(category,rows):
    if not rows:return
    color=CATEGORY_COLORS[category];html=[]
    for a in rows:
        url=escape(a["url"],quote=True);image=escape(a["image_url"],quote=True) or img_fallback(color)
        fallback=img_fallback(color)
        html.append(f"<article class='card'><a class='thumb' href='{url}' target='_blank' rel='noopener'><img src='{image}' onerror=\"this.onerror=null;this.src='{fallback}';\" alt='' loading='lazy'></a><div class='body'><div class='meta'><span class='tag'>{escape(category)}</span><span>{escape(ago(a['publishedAt']))}</span></div><div class='headline'><a href='{url}' target='_blank' rel='noopener'>{escape(a['title'])}</a></div><div class='desc'>{escape(a['description'] or 'No description available.')}</div><div class='foot'><span class='source'>{escape(a['source'])}</span><a class='read' href='{url}' target='_blank' rel='noopener'>Read ↗</a></div></div></article>")
    st.markdown(f"<div class='section'><div class='section-title'>{escape(category)}</div><div class='count'>{len(rows):02d} stories</div></div><div class='news-grid'>{''.join(html)}</div>",unsafe_allow_html=True)

def rail(rows):
    sources=Counter(x["source"] for x in rows)
    alerts=sum(1 for x in rows if any(t in f"{x['title']} {x['description']}".lower() for t in ALERT_TERMS))
    st.markdown(f"<div class='rail'><div class='rail-title'>Signal monitor</div><div class='row'><span>Stories</span><b>{len(rows)}</b></div><div class='row'><span>Sources</span><b>{len(sources)}</b></div><div class='row'><span>Priority signals</span><b>{alerts}</b></div><div class='row'><span>Active themes</span><b>04</b></div></div>",unsafe_allow_html=True)
    if sources:
        s=''.join(f"<div class='row'><span>{escape(str(n))}</span><b>{v}</b></div>" for n,v in sources.most_common(6))
        st.markdown(f"<div class='rail'><div class='rail-title'>Source pulse</div>{s}</div>",unsafe_allow_html=True)
    counts={c:sum(1 for x in rows if x["category"]==c) for c in CATEGORIES};peak=max(counts.values(),default=1)
    bars=''.join(f"<div style='margin:9px 0'><div class='row' style='border:0;padding:0'><span>{escape(c)}</span><b>{n}</b></div><div class='bar'><div class='fill' style='width:{int(n/peak*100)}%'></div></div></div>" for c,n in counts.items())
    st.markdown(f"<div class='rail'><div class='rail-title'>Theme distribution</div>{bars}</div>",unsafe_allow_html=True)

logo="<svg viewBox='0 0 32 32' fill='none'><circle cx='14' cy='14' r='8.5' stroke='#C7FF4A' stroke-width='2'/><path d='M20 20l7 7' stroke='#C7FF4A' stroke-width='2.5' stroke-linecap='round'/><path d='M10 16v-3M14 16v-6M18 16V9' stroke='#76F7C5' stroke-width='1.8' stroke-linecap='round'/></svg>"
st.markdown(f"<div class='ai-head'><div class='brand'><div class='mark'>{logo}</div><div><div class='brand-name'>Audit Intelligence</div><div class='brand-sub'>Global Banking Risk · Controls · Regulatory Signals</div></div></div><div class='status'><span class='dot'></span>Live intelligence</div></div>",unsafe_allow_html=True)
st.markdown("<div class='hero'><div class='kicker'>● Executive intelligence layer</div><div class='title'>Banking risk, <span>decoded.</span></div><div class='copy'>A live editorial briefing for transformation, regulation, people and global banking — designed for rapid scanning by audit, risk and control functions.</div><div class='chips'><span class='chip'><b>04</b> themes</span><span class='chip'><b>NewsData.io</b> source</span><span class='chip'><b>05 min</b> cache</span><span class='chip'><b>server-side</b> credential</span></div></div>",unsafe_allow_html=True)

c1,c2,c3,c4=st.columns([2.4,1,1,1],gap="small")
with c1: search=st.text_input("Search",placeholder="Search bank, regulation, AI, audit…",label_visibility="collapsed")
with c2: days=st.selectbox("Window",[1,3,7,14,30],2,format_func=lambda x:f"Last {x} days",label_visibility="collapsed")
with c3: min_rel=st.selectbox("Signal",[0,4,8,12],0,format_func=lambda x:"All signals" if x==0 else f"Signal ≥ {x}",label_visibility="collapsed")
with c4: refresh=st.button("↻ Refresh",use_container_width=True)
if refresh:load_news.clear();st.rerun()
api_key=key()
if not api_key:
    st.error("NewsData.io is not configured. Add NEWSDATA_API_KEY in Streamlit Cloud → App settings → Secrets.")
    st.stop()
with st.spinner("Synchronising intelligence…"): articles,errors,stats=load_news(api_key,days,min_rel,tuple(CATEGORIES))
if search:
    q=search.lower().strip();articles=[a for a in articles if q in f"{a['title']} {a['description']} {a['source']} {a['category']}".lower()]
sources=len(set(a["source"] for a in articles))
st.markdown(f"<div class='chips'><span class='chip'><b>{len(articles):02d}</b> stories</span><span class='chip'><b>{sources:02d}</b> sources</span><span class='chip'>Updated <b>{datetime.now(timezone.utc).strftime('%d %b %Y · %H:%M UTC')}</b></span></div>",unsafe_allow_html=True)
main,side=st.columns([2.45,1],gap="large")
with main:
    if not articles:st.markdown("<div class='rail' style='margin-top:24px;text-align:center;padding:45px'><div class='rail-title'>No matching intelligence</div><div style='color:#718980;font-size:10px'>Expand the window or change the search term.</div></div>",unsafe_allow_html=True)
    for cat in CATEGORIES:cards(cat,[a for a in articles if a["category"]==cat])
with side:
    rail(articles)
    if articles:
        st.download_button("Download briefing CSV",pd.DataFrame(articles).to_csv(index=False).encode(),f"audit_intelligence_{datetime.now().strftime('%Y%m%d_%H%M')}.csv","text/csv",use_container_width=True)
if errors:
    with st.expander("System diagnostics"):
        for e in errors:st.write(e)
st.markdown("<div class='app-foot'><span>AUDIT INTELLIGENCE · INTERNAL BRIEFING</span><span>NewsData.io · Server-side credential · Executive research interface</span></div>",unsafe_allow_html=True)
