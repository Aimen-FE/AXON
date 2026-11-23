import asyncio,json
import httpx
from app.ai import OllamaAdapter
from app.config import Settings
from app.models import ProviderPolicy
from app import providers

async def fake_status():return {'available':True,'models':['fixture-local'],'model':'fixture-local'}

def test_runtime_config_no_credentials_leak_and_cloud_contract(login,app,monkeypatch):
    admin=login('admin.demo');student=login();monkeypatch.setattr(app.state.ai,'status',fake_status)
    seen=[];real_client=httpx.AsyncClient
    def handler(request):
        seen.append(request)
        if request.url.path.endswith('/models'):return httpx.Response(200,json={'data':[{'id':'fixture-cloud','active':True}],'models':[{'name':'models/fixture-cloud','supportedGenerationMethods':['generateContent']}]})
        if 'generateContent' in request.url.path:return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':'Respuesta pública de contrato'}]}}]})
        return httpx.Response(200,json={'choices':[{'message':{'content':'Respuesta pública de contrato'}}]})
    monkeypatch.setattr(providers.httpx,'AsyncClient',lambda *a,**k:real_client(*a,**k,transport=httpx.MockTransport(handler)))
    for version,provider in enumerate(('gemini','groq')):
        monkeypatch.setenv(providers.KEYS[provider],'fixture-key-never-real')
        payload={'version':version,'local':{'model':'fixture-local'},'cloud':{'provider':provider,'enabled':True,'model':'fixture-cloud'}}
        assert student.put('/api/ai/providers',json=payload).status_code==403
        r=admin.put('/api/ai/providers',json=payload);assert r.status_code==200,r.text
        assert 'fixture-key' not in r.text and r.json()['private_chat_provider']=='ollama'
        assert student.post('/api/ai/public-prompt',json={'query':'Explica la fotosíntesis','consent':False}).status_code==422
        r=student.post('/api/ai/public-prompt',json={'query':'Explica la fotosíntesis','consent':True});assert r.status_code==200,r.text
        assert r.json()['private_context_forwarded'] is False
        body=json.loads(seen[-1].content);assert 'memories' not in body and 'history' not in body and 'documents' not in body and 'tools' not in body
        assert '30 minutos' not in seen[-1].content.decode()
    assert len([r for r in seen if r.method=='POST'])==2

def test_local_queue_limit_timeout_cancellation_and_recovery():
    async def check():
        adapter=OllamaAdapter(Settings.from_env());entered=asyncio.Event()
        async def waiting():
            async with adapter.slot(.05):return 'unexpected'
        async with adapter.slot(.05):
            tasks=[asyncio.create_task(waiting()) for _ in range(3)]
            await asyncio.sleep(.01)
            assert adapter.active==1 and adapter.waiting==3
            try:
                async with adapter.slot(.05):pass
                assert False
            except TimeoutError:pass
            tasks[0].cancel()
            results=await asyncio.gather(*tasks,return_exceptions=True)
            assert sum(isinstance(r,TimeoutError) for r in results)==2
        assert adapter.active==0 and adapter.waiting==0
        async with adapter.slot(.05):assert adapter.active==1
    asyncio.run(check())
