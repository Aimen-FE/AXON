"""End-to-end authorization checks for the native class routes."""
import secrets
from datetime import timedelta


from app.class_models import LearningClass
from app.db import utcnow


def create_class(teacher, name='Laboratorio nativo', subject=None):
    academic = teacher.get('/api/academic').json()
    group = next(item for item in academic['groups'] if 'Bachillerato' in item['name'])
    actual = next(item for item in academic['subjects'] if item['name'] == (subject or 'Matemáticas'))
    response = teacher.post('/api/classes', json={
        'name': name, 'group_id': group['id'], 'subject_id': actual['id'], 'description': 'Investigación escolar ficticia',
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_class_roster_and_course_authorization(app, login):
    teacher = login('profesor.demo')
    other = login('profesora.demo')
    admin = login('admin.demo')
    student = login('alumno.demo')
    second = login('alumna.demo')
    room = create_class(teacher)
    path = '/api/classes/' + room['id']
    with app.state.session_factory() as db:
        stored = db.get(LearningClass, room['id'])
        assert stored.join_hash != room['join_code']

    assert other.get(path).status_code == 404
    assert student.get(path).status_code == 404
    assert student.post('/api/classes', json={k: room[k] for k in ('name', 'group_id', 'subject_id')}).status_code == 403
    denied = other.post('/api/classes', json={k: room[k] for k in ('name', 'group_id', 'subject_id')})
    assert denied.status_code == 403
    assert student.post('/api/classes/join', json={'code': secrets.token_urlsafe(18)}).status_code == 404
    assert student.post('/api/classes/join', json={'code': room['join_code']}).status_code == 200
    assert student.post('/api/classes/join', json={'code': room['join_code']}).status_code == 200
    assert student.post(path + '/teachers', json={'username': 'alumno.demo'}).status_code == 403
    assert student.get(path + '/people').json()['members'] == [
        {'id': student.user['id'], 'name': student.user['display_name'], 'role': 'student'},
        {'id': teacher.user['id'], 'name': teacher.user['display_name'], 'role': 'teacher'},
    ]
    assert admin.get(path).status_code == 200
    assert teacher.post(path + '/invitations', json={'username': 'alumna.demo'}).status_code == 201
    assert second.get('/api/classes').json()['invitations'][0]['id'] == room['id']
    assert second.post(path + '/accept').status_code == 200
    assert second.get('/api/classes').json()['invitations'] == []
    assert teacher.delete(path + '/members/' + student.user['id']).status_code == 200
    assert student.post('/api/classes/join', json={'code': room['join_code']}).status_code == 404
    assert student.get(path).status_code == 404
    assert teacher.post(path + '/teachers', json={'username': 'profesora.demo'}).status_code == 201
    assert other.get(path).json()['can_manage']
    assert 'join_hash' not in other.get(path).json()
    new_code = admin.post(path + '/join-code').json()['join_code']
    assert new_code != room['join_code']
    assert admin.put(path + '/archive', json={'archived': True}).json()['archived']
    assert second.get(path).status_code == 200
    assert teacher.patch(path, json={'name': 'Renombrada'}).status_code == 409


def test_posts_and_topics_stay_inside_their_class(login):
    teacher = login('profesor.demo')
    student = login('alumno.demo')
    room = create_class(teacher)
    second_room = create_class(teacher, 'Otro laboratorio')
    path = '/api/classes/' + room['id']
    other_path = '/api/classes/' + second_room['id']
    assert student.post('/api/classes/join', json={'code': room['join_code']}).status_code == 200
    notice = {'title': 'Salida del martes', 'content': 'Traed el diario de campo.', 'pinned': True}
    assert student.post(path + '/posts', json=notice).status_code == 403
    post = teacher.post(path + '/posts', json=notice).json()
    comments = path + '/posts/' + post['id'] + '/comments'
    assert student.post(comments, json={'content': '¿A qué hora?'}).status_code == 403
    assert teacher.get(other_path + '/posts/' + post['id'] + '/comments').status_code == 404
    notice['comments_open'] = True
    assert teacher.put(path + '/posts/' + post['id'], json=notice).status_code == 200
    comment = student.post(comments, json={'content': '¿A qué hora?'}).json()
    assert teacher.get(comments).json()[0]['id'] == comment['id']
    assert teacher.delete(comments + '/' + comment['id']).status_code == 200
    assert student.get(comments).json() == []
    assert student.get('/api/notifications').json()[0]['category'] == 'class'
    assert teacher.post(path + '/topics', json={'name': 'Cuaderno'}).status_code == 201
    assert student.get(other_path + '/topics').status_code == 404


def join(client, room):
    response = client.post('/api/classes/join', json={'code': room['join_code']})
    assert response.status_code == 200, response.text


def draft_activity(teacher, path, **overrides):
    body = {
        'title': 'Diario de laboratorio', 'instructions': 'Explica el método usado.',
        'due_at': (utcnow() + timedelta(days=3)).isoformat(), 'max_points': 10,
    }
    response = teacher.post(path + '/activities', json=body | overrides)
    assert response.status_code == 201, response.text
    return path + '/activities/' + response.json()['id'], response.json()


def publish(teacher, path):
    response = teacher.put(path + '/state', json={'status': 'published'})
    assert response.status_code == 200, response.text
    return response.json()


def test_materials_assistance_and_documents_respect_class_scope(app, login, monkeypatch):
    teacher = login('profesor.demo')
    student = login('alumno.demo')
    other = login('alumna.demo')
    rooms = [create_class(teacher), create_class(teacher, 'Otro laboratorio')]
    path, other_path = ['/api/classes/' + room['id'] for room in rooms]
    join(student, rooms[0])
    join(other, rooms[1])
    topic = teacher.post(other_path + '/topics', json={'name': 'Datos reservados'}).json()
    upload = {'file': ('guia.txt', b'La refraccion modifica la trayectoria de la luz.', 'text/plain')}
    assert teacher.post(path + '/files', data={'title': 'Guía', 'topic_id': topic['id']}, files=upload).status_code == 404
    assert other.post(path + '/files', data={'title': 'Guía'}, files=upload).status_code == 403
    material = teacher.post(path + '/files', data={'title': 'Refracción'}, files=upload)
    assert material.status_code == 201, material.text
    doc_id = material.json()['id']
    confidential = teacher.post(other_path + '/files', data={'title': 'Refracción reservada'},
        files={'file': ('otra.txt', b'Refraccion y marca reservada: sombra azul.', 'text/plain')}).json()['id']
    assert {doc['id'] for doc in student.get(path + '/files').json()} == {doc_id}
    assert student.get('/api/documents/' + confidential + '/chunks').status_code == 404
    download = student.get('/api/documents/' + doc_id + '/download')
    assert download.content == upload['file'][1]
    assert download.headers['cache-control'] == 'no-store'
    assert download.headers['content-disposition'].startswith('attachment;')
    assert teacher.delete('/api/documents/' + doc_id).status_code == 409

    async def generate(history, context):
        assert {item['document_id'] for item in context['documents']} == {doc_id}
        assert context['memories'] == []
        return 'La trayectoria de la luz cambia [fuente:1]. [fuente:9]', 'ollama'

    monkeypatch.setattr(app.state.ai, 'generate', generate)
    reply = student.post(path + '/assist', json={'mode': 'explain', 'prompt': 'Refracción'}).json()
    assert [item['document_id'] for item in reply['citations']] == [doc_id]
    assert '[fuente:' not in reply['content'] and 'sombra azul' not in reply['content']
    assert student.post(path + '/assist', json={'mode': 'feedback', 'prompt': 'Corrección'}).status_code == 403
    assert student.post(other_path + '/assist', json={'mode': 'explain', 'prompt': 'Refracción'}).status_code == 404

    result = student.post('/api/tools/call', json={'tool': 'query_classes', 'arguments': {}}).json()
    assert [item['id'] for item in result['result']] == [rooms[0]['id']]
    assert [item['id'] for item in student.get('/api/atlas/layers').json()['academic']['classes']] == [rooms[0]['id']]
    conversation = student.post('/api/conversations', json={'title': 'Mis clases'}).json()
    message = student.post(f"/api/conversations/{conversation['id']}/messages",
                           json={'content': '¿Qué clases tengo?', 'client_id': secrets.token_urlsafe(12)})
    assert message.status_code == 200 and rooms[0]['name'] in message.text and rooms[1]['name'] not in message.text


def test_quiz_submission_grade_and_private_file_history(login, monkeypatch):
    teacher = login('profesor.demo')
    student = login()
    other = login('alumna.demo')
    room = create_class(teacher)
    path = '/api/classes/' + room['id']
    for learner in (student, other):
        join(learner, room)
    item_path, item = draft_activity(teacher, path, kind='quiz', questions=[
        {'prompt': '¿Qué es una hipótesis?', 'options': ['Una suposición', 'Un resultado']},
        {'prompt': 'Escribe un ejemplo'},
    ], rubric=[{'title': 'Comprensión', 'points': 6}, {'title': 'Explicación', 'points': 4}])
    assert student.get(item_path).status_code == 404
    assert teacher.post(path + '/files', data={'title': 'Hoja', 'activity_id': item['id']},
                         files={'file': ('hoja.txt', b'Instrucciones modelo.', 'text/plain')}).status_code == 201
    publish(teacher, item_path)
    assert student.get(item_path).json()['files'][0]['title'] == 'Hoja'
    assert any(task['id'] == item['id'] and task.get('class_id') == room['id']
               for task in student.get('/api/assignments').json())
    assert student.get(path + '/calendar').json()[0]['activity_id'] == item['id']
    assert any(event['title'] == item['title'] for event in student.get('/api/events').json())
    endpoint = item_path + '/submission'
    draft = student.put(endpoint, json={'version': 0, 'answers': ['Una suposición'], 'content': 'Borrador privado'}).json()
    assert draft['status'] == 'draft'
    assert teacher.get(item_path + '/submissions').json() == []
    sid_path = item_path + '/submissions/' + draft['id']
    assert teacher.get(sid_path + '/history').status_code == 404
    files = student.post(endpoint + '/files', data={'version': draft['version']},
                         files={'file': ('evidencia.txt', b'Registro privado', 'text/plain')})
    assert files.status_code == 201, files.text
    attachment = files.json()
    doc_id = attachment['files'][0]['id']
    download = sid_path + '/files/' + doc_id
    assert teacher.get(download).status_code == 404
    assert other.get(download).status_code == 404
    assert student.get('/api/documents/' + doc_id + '/download').status_code == 404
    assert student.get(download).content == b'Registro privado'
    assert student.put(endpoint, json={'version': draft['version'], 'content': 'Desactualizado'}).status_code == 409
    assert student.put(endpoint, json={'version': attachment['version'], 'submit': True,
                                      'answers': ['Una suposición']}).status_code == 422
    final = student.put(endpoint, json={'version': attachment['version'], 'submit': True,
                                       'answers': ['Una suposición', 'La temperatura afecta al cultivo.']})
    assert final.status_code == 200, final.text
    work = final.json()
    assert teacher.get(download).content == b'Registro privado'
    assert other.get(sid_path + '/history').status_code == 404
    assert student.post(sid_path + '/return', json={'version': work['version'], 'feedback': 'Manipulación'}).status_code == 403
    assert teacher.post(sid_path + '/return', json={'version': work['version'], 'feedback': 'Revisado',
                                                   'criteria_scores': [7, 4]}).status_code == 422
    grade = teacher.post(sid_path + '/return', json={'version': work['version'], 'feedback': 'Revisado',
                                                   'criteria_scores': [5, 4]})
    assert grade.status_code == 200, grade.text
    assert grade.json()['grade']['points'] == 9
    assert [row['change'] for row in teacher.get(sid_path + '/history').json()] == ['returned', 'submitted']
    assert [row['change'] for row in student.get(sid_path + '/history').json()] == ['returned', 'submitted', 'file_added', 'draft']
    assert student.get(path + '/grades').json()[0]['points'] == 9
    assert other.get(path + '/grades').json() == []
    future = utcnow() + timedelta(days=4)
    monkeypatch.setattr('app.classwork.utcnow', lambda: future)
    response = student.put(endpoint, json={'version': grade.json()['version'], 'content': 'Fuera de plazo', 'submit': True})
    assert response.status_code == 409 and 'plazo' in response.json()['detail']


def test_shared_team_work_keeps_version_and_never_leaks_to_other_teams(login):
    teacher, first, second, outsider = (login(name) for name in ('profesor.demo', 'alumno.demo', 'alumna.demo', 'alumno2.demo'))
    room = create_class(teacher)
    path = '/api/classes/' + room['id']
    for learner in (first, second, outsider):
        join(learner, room)
    users = [first.user['id'], second.user['id']]
    assert teacher.post(path + '/teams', json={'name': 'Equipo A', 'students': users}).status_code == 201
    assert teacher.post(path + '/teams', json={'name': 'Equipo B', 'students': [users[0], outsider.user['id']]}).status_code == 409
    item_path, item = draft_activity(teacher, path, delivery='team')
    publish(teacher, item_path)
    draft = first.put(item_path + '/submission', json={'version': 0, 'content': 'Propuesta colectiva'}).json()
    assert second.get(item_path + '/submission').json()['id'] == draft['id']
    assert outsider.get(item_path + '/submission').json() is None
    assert outsider.put(item_path + '/submission', json={'version': draft['version'], 'content': 'Acceso'}).status_code == 409
    submitted = second.put(item_path + '/submission', json={'version': draft['version'], 'content': 'Trabajo final',
                                                           'submit': True}).json()
    reviewed = teacher.post(item_path + '/submissions/' + submitted['id'] + '/return',
                            json={'version': submitted['version'], 'feedback': 'Bien', 'points': 8})
    assert reviewed.status_code == 200, reviewed.text
    assert first.get(path + '/grades').json()[0]['points'] == second.get(path + '/grades').json()[0]['points'] == 8
    assert not outsider.get(path + '/grades').json()


def test_exam_schedule_hides_instructions_and_attachments_until_start(login):
    teacher, student = login('profesor.demo'), login()
    room = create_class(teacher)
    path = '/api/classes/' + room['id']
    join(student, room)
    item_path, item = draft_activity(teacher, path, kind='exam', exam_at=(utcnow() + timedelta(hours=2)).isoformat(),
                                    instructions='Contenido reservado')
    file = teacher.post(path + '/files', data={'title': 'Guía del examen', 'activity_id': item['id']},
                        files={'file': ('hoja.txt', b'Preguntas futuras.', 'text/plain')}).json()
    publish(teacher, item_path)
    assert student.get(item_path).json()['locked']
    assert student.get(item_path).json()['instructions'] == ''
    assert student.get('/api/documents/' + file['id'] + '/download').status_code == 404
    assert student.put(item_path + '/submission', json={'version': 0, 'content': 'Antes de tiempo'}).status_code == 409
    events = student.get(path + '/calendar').json()
    assert {event['kind'] for event in events} == {'exam', 'assignment'}
    assert all('Contenido reservado' not in event['description'] for event in events)
    assert teacher.delete(path + '/calendar/' + events[0]['id']).status_code == 404


def test_standalone_class_event_preserves_shared_calendar_and_workspace_permissions(login):
    teacher, student, other = login('profesor.demo'), login(), login('profesora.demo')
    room = create_class(teacher)
    path = '/api/classes/' + room['id']
    join(student, room)
    start = utcnow() + timedelta(days=1)
    body = {'title': 'Sesión de laboratorio', 'kind': 'session', 'starts_at': start.isoformat(),
            'ends_at': (start + timedelta(minutes=45)).isoformat()}
    assert student.post(path + '/calendar', json=body).status_code == 403
    event = teacher.post(path + '/calendar', json=body).json()
    assert student.get('/api/events/' + event['id']).json()['class_id'] == room['id']
    assert other.get('/api/events/' + event['id']).status_code == 404
    assert teacher.post('/api/tools/call', json={'tool': 'cancel_event', 'arguments': {
        'event_id': event['id'], 'version': event['version'],
    }}).status_code == 409
    assert teacher.delete(path + '/calendar/' + event['id']).status_code == 200
    assert student.get('/api/events/' + event['id']).json()['status'] == 'cancelled'


def test_admission_approval_revocation_expiry_and_teacher_permission(login, monkeypatch):
    admin,teacher,student,second=(login(name) for name in ('admin.demo','profesor.demo','alumno.demo','alumna.demo'))
    room=create_class(teacher)
    path='/api/classes/'+room['id']
    assert student.put(path+'/admission',json={}).status_code==403
    assert admin.put(path+'/admission',json={'teacher_invitations':False,'review_codes':True,'code_limit':1}).status_code==200
    assert teacher.post(path+'/invitations',json={'username':'alumna.demo'}).status_code==403
    assert teacher.post(path+'/join-code').status_code==403
    assert admin.put(path+'/admission',json={'teacher_invitations':True,'review_codes':True,'code_limit':1}).status_code==200
    pending=student.post('/api/classes/join',json={'code':room['join_code']})
    assert pending.status_code==200 and pending.json()['pending']
    assert student.get(path).status_code==404
    request=teacher.get(path+'/requests').json()[0]
    assert teacher.post(path+'/requests/'+request['id'],json={'approve':True}).status_code==200
    assert student.get(path).status_code==200
    assert teacher.post(path+'/invitations',json={'username':'alumna.demo'}).status_code==201
    invitation=teacher.get(path+'/invitations').json()[0]
    assert teacher.delete(path+'/invitations/'+invitation['id']).status_code==200
    assert second.post(path+'/accept').status_code==404
    code=admin.post(path+'/join-code').json()['join_code']
    future=utcnow()+timedelta(days=8)
    monkeypatch.setattr('app.classes.utcnow',lambda:future)
    assert second.post('/api/classes/join',json={'code':code}).status_code==404
