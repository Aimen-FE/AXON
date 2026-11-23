from datetime import datetime,timedelta,time
import hashlib
from pathlib import Path
from sqlalchemy import select
from .models import *
from .auth import ph
from .db import utcnow
from .memory import MADRID

DEMO_ACCOUNTS = (
    ('admin.demo', 'Nora Quásar', 'admin'),
    ('profesor.demo', 'Ivo Lumen', 'teacher'),
    ('profesora.demo', 'Lyra Nimbo', 'teacher'),
    ('alumno.demo', 'Ari Cometa', 'student'),
    ('alumna.demo', 'Vela Órbita', 'student'),
    ('alumno2.demo', 'Teo Cúmulo', 'student'),
)


def seed_demo(db,settings,passwords=None):
    if not settings.demo:return False
    if db.scalar(select(Center.id)):return False
    center=Center(name='Centro Educativo Nébula',town='Villa Prisma',settings={'fictional':True,'country':'territorio ficticio','code':'DEMO-001','bathroom_retention_days':14,'automation_enabled':True,'conversation_retention_days':0})
    db.add(center);db.flush()
    year=AcademicYear(center_id=center.id,name='2026–2027');db.add(year);db.flush()
    courses=[Course(center_id=center.id,year_id=year.id,name='1.º Bachillerato',stage='Bachillerato'),Course(center_id=center.id,year_id=year.id,name='2.º ESO',stage='ESO')]
    db.add_all(courses);db.flush()
    groups=[Group(center_id=center.id,course_id=courses[0].id,name='1.º Bachillerato A'),Group(center_id=center.id,course_id=courses[1].id,name='2.º ESO B')]
    db.add_all(groups);db.flush()
    subjects=[Subject(center_id=center.id,name=n,color=c) for n,c in [('Matemáticas','#147d73'),('Lengua Castellana','#8763b3'),('Física y Química','#b77a28'),('Historia','#5271b5')]]
    rooms=[Classroom(center_id=center.id,name='Aula 101'),Classroom(center_id=center.id,name='Aula 202')]
    db.add_all(subjects+rooms);db.flush()
    passwords = passwords or {}
    hashes = {password: ph.hash(password) for password in set(passwords.values())}
    users = [User(center_id=center.id, username=username, display_name=name, role=role,
                  password_hash=hashes[passwords[username]] if username in passwords else '',
                  active=username in passwords, is_demo=True,
                  preferences={'theme': 'dark', 'notifications': {}, 'automatic_personal_actions': True})
             for username, name, role in DEMO_ACCOUNTS]
    db.add_all(users);db.flush()
    admin,teacher,teacher2,student,student2,student3=users
    db.add_all([Enrollment(user_id=student.id,group_id=groups[0].id),Enrollment(user_id=student2.id,group_id=groups[0].id),Enrollment(user_id=student3.id,group_id=groups[1].id)])
    for group in groups:
        for i,subject in enumerate(subjects):db.add(Teaching(teacher_id=teacher.id if i%2==0 else teacher2.id,group_id=group.id,subject_id=subject.id))
    # Deliberately partial sample timetable; review reports must identify missing days.
    for gidx,group in enumerate(groups):
        for day in range(3 if gidx else 5):
            for slot in range(2):
                subject=subjects[(day+slot)%4]
                idx=subjects.index(subject)
                hour=8+slot+gidx*3
                db.add(Schedule(center_id=center.id,group_id=group.id,subject_id=subject.id,
                    teacher_id=teacher.id if idx%2==0 else teacher2.id,classroom_id=rooms[gidx].id,weekday=day,
                    starts=f'{hour:02d}:30',ends=f'{hour+1:02d}:20',source='Datos ficticios de demostración'))
    today=utcnow().astimezone(MADRID).date()
    offset=(0-today.weekday())%7
    next_monday=today+timedelta(days=offset or 7)
    for i,(title,sub,delta,syllabus) in enumerate([('Funciones y gráficas',subjects[0],1,'Funciones afines, cuadráticas y representación gráfica'),('Comentario de texto',subjects[1],3,'Estructura, tema y argumentación'),('Energía y movimiento',subjects[2],8,'Trabajo, energía cinética y conservación')]):
        start=datetime.combine(next_monday+timedelta(days=delta),time(10+i,0),MADRID)
        e=CalendarEvent(center_id=center.id,owner_id=teacher.id if i%2==0 else teacher2.id,group_id=groups[0].id,
            subject_id=sub.id,title=title,description='Examen ficticio para demostrar AXON',kind='exam',visibility='group',starts_at=start,ends_at=start+timedelta(hours=1),source='Calendario ficticio de demostración')
        db.add(e);db.flush();db.add(Exam(event_id=e.id,syllabus=syllabus))
    for i,(title,desc) in enumerate([('Problemas de funciones','Resuelve las actividades 1 a 6. Explica cada paso.'),('Lectura y comentario','Lee el texto y redacta un comentario de 200 palabras.'),('Práctica de laboratorio','Prepara la tabla de observaciones del experimento.')]):
        db.add(Assignment(center_id=center.id,group_id=groups[0].id,subject_id=subjects[i].id,creator_id=teacher.id if i%2==0 else teacher2.id,title=title,description=desc,due_at=datetime.combine(next_monday+timedelta(days=i),time(20),MADRID)))
    text=('# Guía de Matemáticas · DEMOSTRACIÓN\n\nUna ecuación de primer grado es una igualdad con una incógnita cuyo exponente es uno. Para resolverla se realizan operaciones equivalentes en ambos miembros.\n\nEjemplo: 2x + 6 = 14. Restamos 6 a ambos miembros: 2x = 8. Dividimos entre 2: x = 4. Comprobación: 2·4 + 6 = 14.\n\nPara estudiar funciones, identifica el dominio, los cortes con los ejes y los intervalos de crecimiento. Dibuja una tabla de valores antes de representar la gráfica.\n\nEsta guía es ficticia y no constituye un temario oficial del instituto.')
    uploads=settings.data_dir/'uploads';uploads.mkdir(parents=True,exist_ok=True,mode=0o700)
    key='demo-matematicas.md';(uploads/key).write_text(text,encoding='utf-8');(uploads/key).chmod(0o600)
    doc=Document(center_id=center.id,owner_id=teacher.id,group_id=groups[0].id,subject_id=subjects[0].id,title='Guía de Matemáticas · Demo',filename='guia-matematicas.md',storage_key=key,checksum=hashlib.sha256(text.encode()).hexdigest(),access='group',status='validated',source='Material ficticio de demostración',size=len(text.encode()))
    db.add(doc);db.flush();db.add(DocumentChunk(document_id=doc.id,ordinal=0,content=text,location='Guía · fragmento 1'))
    # Provisional institutional source creates an actionable report finding.
    value='Propuesta ficticia de normas de biblioteca. Pendiente de aprobación; no es información oficial.'
    (uploads/'demo-biblioteca.txt').write_text(value,encoding='utf-8');(uploads/'demo-biblioteca.txt').chmod(0o600)
    d2=Document(center_id=center.id,owner_id=admin.id,title='Borrador de biblioteca · Demo',filename='biblioteca.txt',storage_key='demo-biblioteca.txt',checksum=hashlib.sha256(value.encode()).hexdigest(),access='center',status='provisional',source='Borrador ficticio',size=len(value.encode()))
    db.add(d2);db.flush();db.add(DocumentChunk(document_id=d2.id,ordinal=0,content=value,location='Texto · fragmento 1'))
    for u in users:
        db.add(Notification(user_id=u.id,title='Bienvenido a AXON',content='Este entorno utiliza exclusivamente datos y cuentas ficticios. Empieza por el asistente o consulta tu agenda.',category='event'))
    db.add(Memory(user_id=student.id,content='Prefiero estudiar por la tarde en sesiones de 30 minutos.',category='preference'))
    convo=Conversation(user_id=student.id,title='Mi organización de estudio');db.add(convo);db.flush()
    db.add_all([Message(conversation_id=convo.id,role='user',content='Recuerda que prefiero estudiar por la tarde.'),Message(conversation_id=convo.id,role='assistant',content='He guardado tu preferencia en tu memoria privada.',details={'engine':'demo_seed'})])
    return True
