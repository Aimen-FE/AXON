#!/usr/bin/env python3
"""Explicit local test against a fictitious instance. Never uses the personal DB."""
import argparse,asyncio,json,time,secrets
from pathlib import Path
import httpx,psutil

async def run(base,output):
    if base!='http://127.0.0.1:8014':raise ValueError('Este ensayo solo admite la instancia ficticia local 8014')
    # The instance must advertise demo data; check before creating anything.
    async with httpx.AsyncClient(base_url=base,trust_env=False,timeout=90) as client:
        info=(await client.get('/api/public/info')).json()
        if info.get('demo') is not True:raise ValueError('Se necesita una instancia ficticia')
    results=[]
    async def request(index,barrier):
        async with httpx.AsyncClient(base_url=base,trust_env=False,timeout=95) as c:
            r=await c.post('/api/auth/login',json={'username':f'carga{index}.ficticia','password':'CargaFicticia!2030'})
            if r.status_code!=200:raise ValueError('Prepara las cuentas ficticias del ensayo antes de ejecutarlo')
            c.headers['x-csrf-token']=r.json()['csrf_token']
            r=await c.post('/api/conversations',json={'title':'Ensayo ATLAS ficticio'});r.raise_for_status();convo=r.json()['id']
            await barrier.wait();start=time.monotonic()
            r=await c.post('/api/conversations/'+convo+'/messages',json={'content':'Responde en una sola frase de menos de quince palabras: explica qué es la fotosíntesis.','client_id':secrets.token_hex(12)})
            answer=r.json().get('assistant_message',{}) if r.status_code==200 else {}
            return {'user':index,'http':r.status_code,'duration_seconds':round(time.monotonic()-start,3),'engine':answer.get('details',{}).get('engine'),'characters':len(answer.get('content',''))}
    for count in (1,3,5,10):
        if psutil.virtual_memory().available<2*1024**3:results.append({'users':count,'aborted':'available RAM below 2 GiB'});break
        samples=[];stop=asyncio.Event()
        async def sample():
            while not stop.is_set():
                mem=psutil.virtual_memory();samples.append({'cpu':psutil.cpu_percent(),'ram_used_mb':round(mem.used/1024**2),'ram_available_mb':round(mem.available/1024**2)})
                if mem.available<1500*1024**2:raise RuntimeError('Memory safety threshold reached')
                try:await asyncio.wait_for(stop.wait(),.5)
                except TimeoutError:pass
        barrier=asyncio.Event();tasks=[asyncio.create_task(request(i,barrier)) for i in range(count)];monitor=asyncio.create_task(sample())
        await asyncio.sleep(.5);start=time.monotonic();barrier.set()
        try:answers=await asyncio.wait_for(asyncio.gather(*tasks),100)
        finally:stop.set();await monitor
        result={'users':count,'wall_seconds':round(time.monotonic()-start,3),'requests':answers,'peak_cpu_percent':max(x['cpu'] for x in samples),'peak_system_ram_used_mb':max(x['ram_used_mb'] for x in samples),'minimum_available_mb':min(x['ram_available_mb'] for x in samples)}
        results.append(result);output.write_text(json.dumps(results,indent=2));print(json.dumps(result),flush=True)
        await asyncio.sleep(2)
    return results

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base-url',default='http://127.0.0.1:8014');p.add_argument('--output',type=Path,required=True);a=p.parse_args();asyncio.run(run(a.base_url,a.output))
