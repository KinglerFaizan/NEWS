import { getStore } from "@netlify/blobs";
import type { Context, Config } from "@netlify/functions";

const QUERIES: Record<string,string> = {
  Transformation: 'bank AND ("digital transformation" OR "core banking" OR "digital banking" OR "artificial intelligence" OR cloud OR automation OR cybersecurity)',
  Regulation: 'bank AND (regulation OR compliance OR supervision OR enforcement OR "money laundering" OR AML OR KYC OR sanctions OR penalty)',
  People: 'bank AND ("chief risk officer" OR "audit committee" OR "internal audit" OR appointed OR resigns OR "new CEO" OR board OR leadership)',
  "Global Banks": 'HSBC OR JPMorgan OR Citigroup OR Barclays OR UBS OR "Deutsche Bank" OR "Goldman Sachs" OR "Standard Chartered" OR "Bank of America" OR Wells Fargo OR Santander',
};

const STOP = new Set(["the","and","for","with","from","that","this","are","was","were","bank","banking","news","new","after","into","over","their","they","has","have","will","its","you","your","about","says"]);
const tokens=(text:string)=>[...new Set((text||"").toLowerCase().match(/[a-z0-9]{3,}/g)||[])].filter(x=>!STOP.has(x));

function classify(a:any){
  const t=(a.title+" "+(a.description||"")).toLowerCase();
  const tests:Record<string,string[]>={
    Transformation:["digital transformation","core banking","digital banking","artificial intelligence","generative ai","machine learning","cloud","automation","cybersecurity","modernization"],
    Regulation:["regulation","regulatory","supervision","enforcement","aml","anti-money laundering","kyc","sanctions","capital requirements","compliance"],
    People:["appointed","appointment","ceo","cfo","cro","ciso","chief audit","internal audit","audit committee","board","director","leadership"],
    "Global Banks":["hsbc","jpmorgan","citigroup","citi","barclays","deutsche bank","ubs","bnp paribas","santander","standard chartered","bank of america","goldman sachs","morgan stanley","wells fargo"],
  };
  const context=["banking","banker","commercial bank","investment bank","central bank","financial institution","financial services","lender","nbfc","deposit","loan","mortgage","rbi","basel","credit risk","liquidity","aml","kyc","money laundering","sanctions","internal audit","audit committee","jpmorgan","hsbc","barclays","ubs","deutsche bank","citigroup"];
  if(!context.some(x=>t.includes(x)))return null;
  let best="Transformation",score=0;
  for(const [cat,terms] of Object.entries(tests)){const s=terms.reduce((n,x)=>n+(t.includes(x)?1:0),0);if(s>score){score=s;best=cat}}
  return score?best:null;
}

function clean(rows){
  const seen=new Set();const out=[];
  for(const a of rows){
    const title=(a.title||"").trim();const url=(a.link||"").trim();
    if(!title||!url)continue;
    const key=title.toLowerCase().replace(/[^a-z0-9 ]/g,"").replace(/\s+/g," ").slice(0,180);
    if(seen.has(key))continue;seen.add(key);
    const category=classify(a);if(!category)continue;
    out.push({id:a.article_id||url,title,description:a.description||"",url,image_url:a.image_url||"",source:a.source_name||a.source_id||"Unknown",published_at:a.pubDate||"",category});
  }
  return out;
}

async function getModel(profile:string){
  const store=getStore("audit-learning",{consistency:"strong"});
  return (await store.get("profiles/"+profile,{type:"json"}))||{likes:0,dislikes:0,positive:{},negative:{}};
}

function scoreStory(story:any,model:any){
  const words=tokens(story.title+" "+story.description);
  let score=0;
  for(const w of words){
    const p=Number(model.positive?.[w]||0),n=Number(model.negative?.[w]||0);
    if(p||n)score += Math.log((p+1)/(n+1));
  }
  return score;
}

async function fetchQuery(q:string){
  const key=Netlify.env.get("NEWSDATA_API_KEY");
  if(!key)throw new Error("NEWSDATA_API_KEY is not configured in Netlify.");
  const u=new URL("https://newsdata.io/api/1/latest");
  u.searchParams.set("apikey",key);u.searchParams.set("q",q);u.searchParams.set("language","en");u.searchParams.set("category","business,technology");u.searchParams.set("size","10");u.searchParams.set("removeduplicate","1");
  const r=await fetch(u);const data=await r.json();
  if(!r.ok||data.status!=="success")throw new Error(data.message||"NewsData.io request failed");
  return data.results||[];
}

export default async (req:Request,_context:Context)=>{
  try{
    const url=new URL(req.url);const category=url.searchParams.get("category");const profile=(url.searchParams.get("profile")||"anonymous").replace(/[^a-zA-Z0-9_-]/g,"").slice(0,80)||"anonymous";
    const queries=category&&QUERIES[category]?[QUERIES[category]]:Object.values(QUERIES);
    const batches=await Promise.all(queries.map(fetchQuery));
    let stories=clean(batches.flat());
    const model=await getModel(profile);
    stories=stories.map(s=>({...s,model_score:scoreStory(s,model)})).sort((a,b)=>b.model_score-a.model_score||new Date(b.published_at).getTime()-new Date(a.published_at).getTime());
    return Response.json({stories,profile:{likes:model.likes||0,dislikes:model.dislikes||0}});
  }catch(e:any){
    return Response.json({error:e?.message||"Unable to load intelligence feed"}, {status:500});
  }
};

export const config:Config={path:"/api/news"};
