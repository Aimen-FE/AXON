from app.models import Center,User,CoreState,CoreRevision
from app.atlas import identity_intent,bootstrap
from app.documents import retrieve_documents
from app.relevance import attributed_citations
from app.db import new_id

def chat(client,text,convo=None):
    convo=convo or client.post('/api/conversations',json={'title':'ATLAS ficticio'}).json()['id']
    response=client.post(f'/api/conversations/{convo}/messages',json={'content':text,'client_id':new_id()})
    assert response.status_code==200,response.text
    return response.json()['assistant_message'],convo

def test_identity_independent_of_model_and_no_irrelevant_citations(login,app):
    c=login();ans,convo=chat(c,'¿De dónde eres?')
    assert 'Centro Educativo Nébula' in ans['content'] and 'Villa Prisma' in ans['content']
    assert 'independiente' in ans['content'] and 'DEMO-001' in ans['content']
    assert ans['details']['engine']=='configured_identity' and ans['details']['citations']==[]
    for text in ('¿A qué instituto perteneces?','¿Y dónde?','¿Y tu centro?','¿Quién eres?','¿Cuál es tu objetivo?','¿Para quién estás pensado?','¿Qué puedes hacer?'):
        ans,convo=chat(c,text,convo);assert ans['details']['engine']=='configured_identity',(text,ans)
    with app.state.session_factory() as db:
        assert retrieve_documents(db,db.get(User,c.user['id']),'¿A qué instituto perteneces?')==[]

def test_core_version_confirmation_restore_and_privilege(login,app):
    admin=login('admin.demo');student=login()
    before=admin.get('/api/atlas/core').json();identity=before['identity']|{'mission':'Ayudar a aprender con un núcleo verificado y trazable.'}
    payload={'version':before['version'],'identity':identity,'reason':'Mejorar la misión en la prueba'}
    assert student.post('/api/atlas/core/propose',json=payload).status_code==403
    result=admin.post('/api/atlas/core/propose',json=payload).json();action=result['action']
    assert admin.get('/api/atlas/core').json()['identity']==before['identity']
    assert admin.post('/api/actions/'+action['id']+'/confirm').status_code==200
    assert admin.post('/api/actions/'+action['id']+'/confirm').status_code==200
    current=admin.get('/api/atlas/core').json();assert current['version']==before['version']+1
    assert admin.post('/api/atlas/core/propose',json=payload).status_code==409
    rollback=admin.post('/api/atlas/core/restore',json={'version':current['version'],'target_version':1}).json()
    assert admin.post('/api/actions/'+rollback['action']['id']+'/confirm').status_code==200
    restored=admin.get('/api/atlas/core').json();assert restored['identity']==before['identity'] and restored['version']==3
    assert len(restored['history'])==3 and restored['principles']==before['principles']
    assert 'history' not in student.get('/api/atlas/core').json()

def test_cross_center_core_not_inherited(app):
    from app.atlas import context
    with app.state.session_factory() as db:
        other=Center(name='Centro independiente de pruebas',town='Villa Delta');db.add(other);db.flush()
        bootstrap(db)
        user=User(center_id=other.id,username='otro',display_name='Otro',password_hash='',role='admin')
        db.add(user);db.flush();result=context(db,user)
        assert result['identity']['center_code']=='' and result['identity']['center_name']==other.name
        assert 'DEMO-001' not in str(result)

def test_attribution_requires_valid_explicit_source():
    docs=[{'document_id':'x','title':'Guía','location':'página 2','status':'validated'}]
    assert attributed_citations('Explicación general',docs)[1]==[]
    answer,cites=attributed_citations('Dato [fuente:1]. No válida [fuente:19]',docs)
    assert len(cites)==1 and '19' not in answer and 'Guía, página 2' in answer
    assert identity_intent('¿Dónde está el centro de una circunferencia?') is None
