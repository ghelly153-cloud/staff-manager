// Thin fetch wrapper. Every mutating call carries the CSRF header; errors surface server messages verbatim.
export class ApiErr extends Error { constructor(status, body){ super(body?.message || ('Request failed ('+status+')')); this.status=status; this.body=body||{}; this.code=body?.code; } }
async function call(method, url, body){
  let r;
  try{ r = await fetch(url,{method,headers:{'X-Requested-With':'emp-app',...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined,credentials:'same-origin'}); }
  catch(e){ throw new ApiErr(0,{message:'You appear to be offline or the server is unreachable. Nothing was saved.',code:'offline'}); }
  if(r.status===401){ location.hash='#/login'; throw new ApiErr(401,{message:'Please sign in.'}); }
  let j=null; try{ j=await r.json(); }catch(e){}
  if(!r.ok){ throw new ApiErr(r.status, j && (j.message||j.detail) ? {message:j.message||j.detail,...j} : {message:'Request failed ('+r.status+')'}); }
  return j;
}
export const api={get:u=>call('GET',u),post:(u,b)=>call('POST',u,b||{}),patch:(u,b)=>call('PATCH',u,b),put:(u,b)=>call('PUT',u,b)};
export const qs=o=>Object.entries(o).filter(([,v])=>v!==undefined&&v!==null&&v!=='').map(([k,v])=>encodeURIComponent(k)+'='+encodeURIComponent(v)).join('&');
