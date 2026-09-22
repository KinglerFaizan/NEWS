const state={view:"All News",stories:[],profile:null};

const $=s=>document.querySelector(s);
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const fmtTime=v=>{if(!v)return"";const d=new Date(v);if(Number.isNaN(d.getTime()))return v;const m=Math.round((Date.now()-d.getTime())/60000);if(m<60)return m+"m ago";if(m<1440)return Math.round(m/60)+"h ago";return Math.round(m/1440)+"d ago"};

function profileId(){let id=localStorage.getItem("audit_ai_profile");if(!id){id=crypto.randomUUID?crypto.randomUUID():Math.random().toString(36).slice(2);localStorage.setItem("audit_ai_profile",id)}return id}

async function loadNews(){
  $("#status").textContent="Fetching fresh banking intelligence…";
  $("#feed").innerHTML='<div class="loading">SYNCING NEWSDATA.IO · ADAPTIVE RANKING…</div>';
  const params=new URLSearchParams({profile:profileId()});
  if(state.view!=="All News")params.set("category",state.view);
  try{
    const r=await fetch("/api/news?"+params.toString(),{cache:"no-store"});
    const data=await r.json();
    if(!r.ok)throw new Error(data.error||"Feed request failed");
    state.stories=data.stories||[];
    state.profile=data.profile||{};
    render();
    $("#updated").textContent="Updated "+new Date().toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"});
    $("#status").textContent="NewsData.io · "+state.stories.length+" unique stories · model score applied";
  }catch(e){
    $("#status").textContent="Feed error: "+e.message;
    $("#feed").innerHTML='<div class="empty">The intelligence feed could not be loaded. Check the Netlify function logs and NewsData.io key.</div>';
  }
}

function render(){
  const stories=state.stories;
  $("#story-count").textContent=stories.length;
  $("#source-count").textContent=new Set(stories.map(x=>x.source).filter(Boolean)).size;
  $("#model-likes").textContent=(state.profile?.likes||0)+" likes";
  $("#model-dislikes").textContent=(state.profile?.dislikes||0)+" not-for-me";
  renderFeatured(stories[0]);
  const visible=stories.slice(1);
  $("#feed").innerHTML="";
  if(!visible.length){$("#feed").innerHTML='<div class="empty">No stories matched this category.</div>';return}
  const tpl=$("#story-template");
  visible.forEach(story=>{
    const node=tpl.content.cloneNode(true);
    const card=node.querySelector(".story-card");
    const img=node.querySelector(".story-image");
    img.src=story.image_url||"/placeholder.svg";img.onerror=()=>{img.src="/placeholder.svg"};
    node.querySelector(".story-category").textContent=story.category;
    node.querySelector(".story-source").textContent=(story.source||"Unknown").toUpperCase();
    node.querySelector(".story-time").textContent=fmtTime(story.published_at);
    node.querySelector(".story-title").textContent=story.title;
    node.querySelector(".story-desc").textContent=story.description||"No description available.";
    const link=node.querySelector(".read-link");link.href=story.url;
    node.querySelector(".like-btn").onclick=()=>feedback(story,true,card);
    node.querySelector(".dislike-btn").onclick=()=>feedback(story,false,card);
    $("#feed").appendChild(node);
  });
}

function renderFeatured(story){
  if(!story){$("#featured").innerHTML="";return}
  $("#featured").innerHTML='<img class="featured-image" src="'+esc(story.image_url||"/placeholder.svg")+'" onerror="this.src=/placeholder.svg" alt="">'+
    '<div class="featured-copy"><div class="featured-kicker">'+esc(story.category)+" · ADAPTIVE TOP STORY</div>"+
    "<h2>"+esc(story.title)+"</h2><p>"+esc(story.description||"")+"</p>"+
    '<a href="'+esc(story.url)+'" target="_blank" rel="noopener noreferrer">Open source article ↗</a></div>';
}

async function feedback(story,liked,card){
  const buttons=card.querySelectorAll("button");buttons.forEach(b=>b.disabled=true);
  try{
    const r=await fetch("/api/feedback",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({
      profile:profileId(),liked,story
    })});
    const data=await r.json();if(!r.ok)throw new Error(data.error||"Feedback failed");
    card.style.opacity=".45";card.style.pointerEvents="none";
    state.profile=data.profile||state.profile;
    $("#model-likes").textContent=(state.profile?.likes||0)+" likes";
    $("#model-dislikes").textContent=(state.profile?.dislikes||0)+" not-for-me";
    $("#status").textContent=liked?"Learned: show more stories with similar signals.":"Learned: reduce similar stories in future rankings.";
  }catch(e){buttons.forEach(b=>b.disabled=false);$("#status").textContent=e.message}
}

document.querySelectorAll(".nav-item").forEach(btn=>btn.onclick=()=>{
  document.querySelectorAll(".nav-item").forEach(x=>x.classList.remove("active"));
  btn.classList.add("active");state.view=btn.dataset.view;
  $("#active-stream").textContent=state.view==="All News"?"Adaptive ranking across all banking categories":state.view+" stream · locally filtered and model-ranked";
  loadNews();
});
$("#refresh").onclick=loadNews;
$("#clear-learning").onclick=async()=>{
  if(!confirm("Reset your learned news preferences?"))return;
  try{await fetch("/api/feedback",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({profile:profileId(),reset:true})});loadNews()}catch(e){$("#status").textContent=e.message}
};
loadNews();
