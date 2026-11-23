from test_memory_chat import send
from conftest import exam_args


def test_structured_model_proposal_still_needs_human_confirmation(app,login,monkeypatch):
    teacher=login('profesor.demo');args=exam_args(teacher)
    async def propose(text,tools,metadata):
        assert not any('content' in g for g in metadata['groups'])
        assert all(t['function']['name']!='run_shell' for t in tools)
        return [('publish_exam',args)]
    monkeypatch.setattr(app.state.ai,'propose',propose)
    conversation=teacher.post('/api/conversations',json={}).json()['id']
    answer=send(teacher,conversation,'Fija una prueba de Matemáticas el 19 de diciembre de 2030 a las 09:00')['assistant_message']
    assert answer['details']['planner']=='ollama'
    assert answer['details']['actions'][0]['status']=='pending'
    assert not any(e['title']=='Examen de regresión' for e in teacher.get('/api/events').json())


def test_model_cannot_bypass_roles_or_force_personal_mutations(app,login,monkeypatch):
    c=login();args=exam_args(c)
    async def propose(text,tools,metadata):
        return [('publish_exam',args)]
    monkeypatch.setattr(app.state.ai,'propose',propose)
    conversation=c.post('/api/conversations',json={}).json()['id']
    answer=send(c,conversation,'Fija una prueba de Matemáticas el 19 de diciembre de 2030 a las 09:00')['assistant_message']
    assert answer['details']['error']
    assert not c.get('/api/actions').json()


def test_model_unavailable_returns_honest_fallback(app,login,monkeypatch):
    async def generate(history,context):return None,'simulated_fallback'
    monkeypatch.setattr(app.state.ai,'generate',generate)
    c=login();conversation=c.post('/api/conversations',json={}).json()['id']
    answer=send(c,conversation,'Hola')['assistant_message']
    assert 'no está disponible' in answer['content']
    assert answer['details']['engine']=='simulated_fallback'
