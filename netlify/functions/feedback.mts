import { getStore } from "@netlify/blobs";
import type { Context, Config } from "@netlify/functions";

const STOP = new Set(["the","and","for","with","from","that","this","are","was","were","bank","banking","news","new","after","into","over","their","they","has","have","will","its","you","your","about","says"]);
const tokens=(text:string)=>[...new Set((text||"").toLowerCase().match(/[a-z0-9]{3,}/g)||[])].filter(x=>!STOP.has(x));

async function load(profile:string){
  const store=getStore("audit-learning",{consistency:"strong"});
  return {store,model:(await store.get("profiles/"+profile,{type:"json"}))||{likes:0,dislikes:0,positive:{},negative:{}}};
}

export default async (req:Request,_context:Context)=>{
  if(req.method!=="POST")return Response.json({error:"POST required"},{status:405});
  try{
    const body=await req.json();
    const profile=(String(body.profile||"anonymous")).replace(/[^a-zA-Z0-9_-]/g,"").slice(0,80)||"anonymous";
    const {store,model}=await load(profile);
    const key="profiles/"+profile;
    if(body.reset){
      await store.delete(key);
      return Response.json({profile:{likes:0,dislikes:0}});
    }
    if(!body.story||typeof body.liked!=="boolean")return Response.json({error:"story and liked are required"},{status:400});
    const words=tokens(String(body.story.title||"")+" "+String(body.story.description||""));
    const bucket=body.liked?"positive":"negative";
    model[bucket]=model[bucket]||{};
    for(const word of words)model[bucket][word]=Number(model[bucket][word]||0)+1;
    model.likes=Number(model.likes||0)+(body.liked?1:0);
    model.dislikes=Number(model.dislikes||0)+(body.liked?0:1);
    await store.setJSON(key,model);
    return Response.json({profile:{likes:model.likes,dislikes:model.dislikes}});
  }catch(e:any){
    return Response.json({error:e?.message||"Unable to save feedback"},{status:500});
  }
};

export const config:Config={path:"/api/feedback"};
