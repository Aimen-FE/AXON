"""Explicit provider boundaries. Private chat always remains on local Ollama."""
import os,re,time,asyncio
from typing import Literal
from collections import defaultdict,deque
import httpx
from fastapi import APIRouter,Depends,HTTPException,Request
from pydantic import BaseModel,Field,ConfigDict
from sqlalchemy import select,update
from .auth import current_user,get_db
from .models import ProviderPolicy
from .policy import require_role,audit
from .db import utcnow
router=APIRouter(prefix='/ai',tags=['Proveedores y recursos de IA'])

class LocalPolicy(BaseModel):
    model_config=ConfigDict(extra='forbid')
    model:str=Field(default='llama3.2:3b',min_length=1,max_length=120,pattern=r'^[\w./:-]+$')
    context_tokens:int=Field(default=4096,ge=2048,le=4096)
    output_tokens:int=Field(default=650,ge=32,le=800)
    timeout_seconds:int=Field(default=60,ge=10,le=75)
    queue_seconds:int=Field(default=12,ge=1,le=20)

class CloudPolicy(BaseModel):
    model_config=ConfigDict(extra='forbid')
    provider:Literal['gemini','groq']='gemini'
    enabled:bool=False
    model:str=Field(default='',max_length=120,pattern=r'^[a-zA-Z0-9._/-]*$')

class PolicyInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:int=Field(ge=0)
    local:LocalPolicy
    cloud:CloudPolicy=Field(default_factory=CloudPolicy)

KEYS={'gemini':'AXON_GEMINI_API_KEY','groq':'AXON_GROQ_API_KEY'}
BASES={'gemini':'https://generativelanguage.googleapis.com/v1beta','groq':'https://api.groq.com/openai/v1'}
_catalog={};cloud_gate=asyncio.Semaphore(1);_calls=defaultdict(deque)

def policy_for(db,user,settings):
    obj=db.scalar(select(ProviderPolicy).where(ProviderPolicy.center_id==user.center_id))
    data=obj.payload if obj else {'local':{'model':settings.ollama_model},'cloud':{}}
    return PolicyInput(version=obj.version if obj else 0,local=data['local'],cloud=data.get('cloud',{}))

def local_policy(db,user,settings):return policy_for(db,user,settings).local.model_dump()

def public_policy(db,user,settings):
    p=policy_for(db,user,settings)
    return p.model_dump()|{'keys_present':{k:bool(os.getenv(v)) for k,v in KEYS.items()},'private_chat_provider':'ollama','cloud_context':'Solo la consulta pública escrita y consentida en esta sección; sin memoria, historial, archivos ni herramientas.','billing':'AXON no crea cuentas, activa facturación ni garantiza cuotas gratuitas.'}

async def remote_models(provider):
    if provider not in KEYS:raise HTTPException(404,'Proveedor no disponible')
    key=os.getenv(KEYS[provider])
    if not key:raise HTTPException(409,'Falta la clave del proveedor en la configuración privada del servidor')
    headers={'x-goog-api-key':key} if provider=='gemini' else {'Authorization':'Bearer '+key}
    try:
        async with httpx.AsyncClient(timeout=8,trust_env=False) as client:
            response=await client.get(BASES[provider]+'/models',headers=headers);response.raise_for_status();payload=response.json()
        models=[x['name'].removeprefix('models/') for x in payload.get('models',[]) if 'generateContent' in x.get('supportedGenerationMethods',[])] if provider=='gemini' else [x['id'] for x in payload.get('data',[]) if x.get('active',True)]
        models=models[:150];_catalog[provider]=(time.monotonic(),models);return models
    except (httpx.HTTPError,ValueError,KeyError):raise HTTPException(502,'No se pudo obtener el catálogo oficial del proveedor')

@router.get('/providers')
async def providers(request:Request,user=Depends(current_user),db=Depends(get_db)):
    import psutil
    ai=request.app.state.ai
    return public_policy(db,user,request.app.state.settings)|{'ollama':await ai.status(),'resources':{'cpu_percent':psutil.cpu_percent(),'ram_used_percent':psutil.virtual_memory().percent,'ram_available_mb':round(psutil.virtual_memory().available/1024**2),'active':ai.active,'waiting':ai.waiting,'queue_capacity':3,'recent_durations_ms':list(ai.measurements)[-12:]}}

@router.get('/models/{provider}')
async def models(provider:str,user=Depends(current_user)):
    require_role(user,'admin');return {'provider':provider,'models':await remote_models(provider)}

@router.put('/providers')
async def configure(body:PolicyInput,request:Request,user=Depends(current_user),db=Depends(get_db)):
    require_role(user,'admin');status=await request.app.state.ai.status()
    if body.local.model not in status.get('models',[]):raise HTTPException(422,'Selecciona un modelo instalado y comprobado en Ollama')
    if body.cloud.enabled:
        available=await remote_models(body.cloud.provider)
        if body.cloud.model not in available:raise HTTPException(422,'Selecciona un modelo del catálogo oficial actual')
    obj=db.scalar(select(ProviderPolicy).where(ProviderPolicy.center_id==user.center_id))
    if (obj.version if obj else 0)!=body.version:raise HTTPException(409,'La configuración ha cambiado; actualiza la página')
    payload=body.model_dump(exclude={'version'})
    if obj:
        changed=db.execute(update(ProviderPolicy).where(ProviderPolicy.id==obj.id,ProviderPolicy.version==body.version).values(payload=payload,version=body.version+1,updated_at=utcnow())).rowcount
        if changed!=1:raise HTTPException(409,'La configuración ha cambiado')
    else:obj=ProviderPolicy(center_id=user.center_id,version=1,payload=payload);db.add(obj);db.flush()
    audit(db,user,'ai_provider_configuration',obj,{'local_model':body.local.model,'cloud_enabled':body.cloud.enabled,'provider':body.cloud.provider});db.commit()
    return public_policy(db,user,request.app.state.settings)

class PublicPrompt(BaseModel):
    model_config=ConfigDict(extra='forbid')
    query:str=Field(min_length=4,max_length=1500)
    consent:bool=False

@router.post('/public-prompt')
async def public_prompt(body:PublicPrompt,request:Request,user=Depends(current_user),db=Depends(get_db)):
    p=policy_for(db,user,request.app.state.settings)
    if not body.consent:raise HTTPException(422,'Autoriza esta consulta pública concreta antes de enviarla al proveedor')
    if not p.cloud.enabled:raise HTTPException(409,'El proveedor externo está desactivado')
    from .research import check_public_query
    check_public_query(db,body.query)
    if re.search(r'\b(mi (?:historial|expediente|nota|contraseña|direccion)|alumno[s]? de|dni|nie|telefono|domicilio)\b',body.query,re.I):raise HTTPException(422,'Escribe un tema público general, sin datos personales ni escolares de personas')
    now=time.monotonic();attempts=_calls[user.id]
    while attempts and attempts[0]<now-3600:attempts.popleft()
    if len(attempts)>=10:raise HTTPException(429,'Límite de diez consultas externas por hora y cuenta')
    attempts.append(now)
    provider=p.cloud.provider;key=os.getenv(KEYS[provider])
    if not key:raise HTTPException(409,'Falta la clave privada del proveedor')
    try:
        await asyncio.wait_for(cloud_gate.acquire(),timeout=.2)
    except TimeoutError:raise HTTPException(429,'Hay otra consulta externa en curso')
    try:
        cached=_catalog.get(provider)
        available=cached[1] if cached and now-cached[0]<300 else await remote_models(provider)
        if p.cloud.model not in available:raise HTTPException(409,'El modelo configurado ya no figura en el catálogo actual')
        system='Responde en español sobre este tema público. No tienes datos privados, herramientas, memoria ni representación institucional. No inventes fuentes ni afirmes haber ejecutado operaciones.'
        async with httpx.AsyncClient(timeout=30,trust_env=False) as client:
            if provider=='groq':
                response=await client.post(BASES[provider]+'/chat/completions',headers={'Authorization':'Bearer '+key},json={'model':p.cloud.model,'messages':[{'role':'system','content':system},{'role':'user','content':body.query}],'max_completion_tokens':500,'stream':False})
                response.raise_for_status();answer=response.json()['choices'][0]['message']['content']
            else:
                response=await client.post(BASES[provider]+'/models/'+p.cloud.model+':generateContent',headers={'x-goog-api-key':key},json={'systemInstruction':{'parts':[{'text':system}]},'contents':[{'role':'user','parts':[{'text':body.query}]}],'generationConfig':{'maxOutputTokens':500}})
                response.raise_for_status();answer=''.join(x.get('text','') for x in response.json()['candidates'][0]['content']['parts'])
        if not answer:raise ValueError()
        return {'answer':answer[:10000],'provider':provider,'model':p.cloud.model,'private_context_forwarded':False,'retained_in_chat':False}
    except (httpx.HTTPError,ValueError,KeyError,IndexError):raise HTTPException(502,'El proveedor no completó la consulta. No se ha usado otro proveedor automáticamente')
    finally:cloud_gate.release()
