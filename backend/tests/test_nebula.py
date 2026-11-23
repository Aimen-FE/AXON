"""Coherence, privacy and usable workflows in the full fictional school."""
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
import secrets
import sqlite3

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.class_models import ClassActivity, ClassGrade, ClassMember, ClassSubmission, LearningClass
from app.config import Settings
from app.db import utcnow
from app.fictionalize import retire
from app.installation import create_local_demo
from app.main import create_app
from app.models import Center, Document, Schedule, User
from app.nebula import populate


@pytest.fixture(scope='module')
def school(tmp_path_factory):
    directory=tmp_path_factory.mktemp('fictional-school')
    initial=replace(Settings.from_env(),data_dir=directory/'empty',database_url=f'sqlite:///{directory}/empty.sqlite3',demo=False)
    path=create_local_demo(initial,directory/'demo')
    passwords={line.split()[0]:line.split(': ',1)[1] for line in path.read_text().splitlines()}
    settings=replace(initial,data_dir=path.parent,database_url=f'sqlite:///{path.parent}/axon.sqlite3',demo=True,ai_mode='simulated')
    app=create_app(settings,maintenance=False)
    yield app,passwords
    app.state.engine.dispose()


@pytest.fixture
def access(school):
    app,passwords=school
    with ExitStack() as stack:
        def login(username):
            client=stack.enter_context(TestClient(app))
            response=client.post('/api/auth/login',json={'username':username,'password':passwords[username]})
            assert response.status_code==200,response.text
            client.headers['X-CSRF-Token']=response.json()['csrf_token']
            client.identity=response.json()['user']
            return client
        yield login


def test_generated_school_coherent_reproducible_and_no_schedule_conflicts(school):
    app,_=school
    with app.state.session_factory() as db:
        center=db.scalar(select(Center))
        first=populate(db,app.state.settings,center.id)
        assert first['center']=='Centro Educativo Nébula' and first['classes']==108 and first['groups']==18
        assert 80 <= first['users'] <= 110
        second=populate(db,app.state.settings,center.id)
        assert first==second
        rows=list(db.scalars(select(Schedule)))
        assert len(rows)==18*6*5
        for field in ('teacher_id','classroom_id','group_id'):
            occupancy=[(row.weekday,row.starts,getattr(row,field)) for row in rows]
            assert len(occupancy)==len(set(occupancy))
        assert db.scalar(select(func.count()).select_from(ClassGrade))>=100
        assert db.scalar(select(ClassActivity.id).where(ClassActivity.due_at<utcnow()))
        for klass in db.scalars(select(LearningClass)):
            members=list(db.scalars(select(ClassMember).where(ClassMember.class_id==klass.id)))
            assert sum(person.role=='student' for person in members)==4
            assert sum(person.role=='teacher' for person in members)==1
        assert {record['stage'] for record in access_programs(db)} >= {'ESO','Bachillerato','FP · Grado Básico','FP · Grado Medio','FP · Grado Superior'}


def access_programs(db):
    from app.models import Course
    return [{'stage':course.stage} for course in db.scalars(select(Course))]


def test_student_teacher_administrator_data_and_internal_solution_privacy(access):
    student,teacher,admin=access('alumno.demo'),access('profesor.demo'),access('admin.demo')
    rooms=student.get('/api/classes').json()['classes']
    assert len(rooms)==6
    assert len(admin.get('/api/classes').json()['classes'])==108
    owned=teacher.get('/api/classes').json()['classes']
    room=next(item for item in rooms if item['id'] in {klass['id'] for klass in owned})
    path='/api/classes/'+room['id']
    activity=student.get(path+'/activities').json()[0]
    activity_path=path+'/activities/'+activity['id']
    assert student.get(activity_path+'/solution').status_code==403
    assert teacher.get(activity_path+'/solution').status_code==200
    other=next(item for item in admin.get('/api/classes').json()['classes'] if item['id'] not in {x['id'] for x in owned})
    assert teacher.get('/api/classes/'+other['id']).status_code==404
    assert len(student.get(path+'/grades').json())>=1
    assert len(teacher.get(path+'/grades').json())>=1
    assert teacher.get('/api/education/overview').json()['pending_reviews']>0
    overview=admin.get('/api/education/overview').json()
    assert overview['classes']==108 and overview['upcoming_evaluations'] and overview['teaching']
    assert admin.get('/api/education/organization').json()['organization']['direction']=='Nora Quásar'
    assert not student.get('/api/education/organization').json()['organization']
    bad=student.put(path+'/evaluation',json={'weights':{'activities':25,'exams':25,'projects':25,'participation':25}})
    assert bad.status_code==403
    core=student.get('/api/atlas/core').json()
    assert core['identity']['center_code']=='DEMO-001' and core['identity']['country']=='territorio ficticio'


def test_controlled_retirement_restores_backup_and_preserves_accounts(tmp_path,app):
    # The marker is synthetic. Production operators supply matching terms in their private manifest.
    app.state.engine.dispose()
    settings=app.state.settings
    with sqlite3.connect(settings.data_dir/'test.sqlite3') as db:
        db.execute("UPDATE centers SET name='Legacy academy marker',town='Legacy location'")
        db.execute("UPDATE core_states SET payload=replace(payload,'Centro Educativo Nébula','Legacy academy marker')")
        before=db.execute('SELECT id,username,password_hash,role,active FROM users ORDER BY id').fetchall()
        db.commit()
    result=retire(settings,{'terms':['Legacy academy marker','Legacy location']},tmp_path.parent/(tmp_path.name+'-private-copy'))
    assert result['centers']==1 and result['documents']>0
    with sqlite3.connect(settings.data_dir/'test.sqlite3') as db:
        assert db.execute('SELECT id,username,password_hash,role,active FROM users ORDER BY id').fetchall()==before
        assert db.execute('SELECT name,town FROM centers').fetchone()==('Centro Educativo Nébula','Villa Prisma')
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
    with sqlite3.connect(tmp_path.parent/(tmp_path.name+'-private-copy')/'restore-check/axon.sqlite3') as restored:
        assert restored.execute('SELECT name FROM centers').fetchone()==('Legacy academy marker',)
