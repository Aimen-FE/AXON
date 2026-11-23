let csrf='';
let onUnauthorized=()=>{};
export function setCsrf(value:string){csrf=value}
export function setUnauthorized(fn:()=>void){onUnauthorized=fn}
export async function api<T>(path:string,options:RequestInit={}):Promise<T>{
 const headers=new Headers(options.headers);
 if(options.body&&!(options.body instanceof FormData))headers.set('Content-Type','application/json');
 if(options.method&&options.method!=='GET')headers.set('X-CSRF-Token',csrf);
 let r:Response;
 try{r=await fetch('/api'+path,{...options,headers,credentials:'same-origin'})}catch{throw new Error('No se puede conectar con AXON. Comprueba que el servidor esté iniciado.')}
 if(!r.ok){
  if(r.status===401&&!path.includes('/auth/login'))onUnauthorized();
  const body=await r.json().catch(()=>({detail:'No se ha podido completar la operación'}));
  const d=body.detail;
  throw new Error(typeof d==='string'?d:Array.isArray(d)?d.map(x=>x.msg).join('. '):d?.message||'Revisa los datos e inténtalo de nuevo');
 }
 return r.json() as Promise<T>;
}
export const post=<T>(path:string,body:unknown={})=>api<T>(path,{method:'POST',body:JSON.stringify(body)});
export const fmt=(date:string,options:Intl.DateTimeFormatOptions={day:'numeric',month:'short'})=>new Intl.DateTimeFormat('es-ES',{timeZone:'Europe/Madrid',...options}).format(new Date(date));
export function localValue(date:string){
 const p=new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Madrid',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(date));
 return p.replace(' ','T');
}
export function madridIso(local:string){
 const [d,t]=local.split('T');if(!d||!t)throw new Error('Completa la fecha y la hora');
 const [y,m,day]=d.split('-').map(Number);const [h,min]=t.split(':').map(Number);
 const target=Date.UTC(y,m-1,day,h,min);let guess=target;
 for(let i=0;i<3;i++){
  const p=new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Madrid',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(guess)).replace(' ','T');
  const parsed=new Date(p+'Z').getTime();guess+=target-parsed;
 }
 if(localValue(new Date(guess).toISOString())!==local.slice(0,16))throw new Error('Esta hora no existe por el cambio de horario. Selecciona otra.');
 return new Date(guess).toISOString();
}
export const roleLabel={student:'Alumno',teacher:'Profesor',admin:'Administración'};

export async function apiBlob(path:string,body:unknown,signal?:AbortSignal):Promise<Blob>{
 const response=await fetch('/api'+path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(body),credentials:'same-origin',signal});
 if(!response.ok){const data=await response.json().catch(()=>({detail:'No se pudo preparar el audio local'}));throw new Error(typeof data.detail==='string'?data.detail:'Revisa la configuración de voz')}
 return response.blob();
}
