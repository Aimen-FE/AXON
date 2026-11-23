"""Reproducible educational simulation. All texts and identities are invented for AXON."""
from datetime import datetime, time, timedelta
from hashlib import sha256

from sqlalchemy import func, select

from .class_calendar import sync_activity_events
from .class_models import (ClassActivity, ClassFile, ClassGrade, ClassMember, ClassPost, ClassRubric,
                           ClassSubmission, ClassTeam, ClassTeamMember, ClassTopic, LearningClass)
from .classwork import save_revision
from .db import utcnow
from .memory import MADRID
from .models import (AcademicYear, Center, Classroom, Course, Document, DocumentChunk, Enrollment,
                     Schedule, Subject, Teaching, User, Group)

CENTER_NAME = 'Centro Educativo Nébula'
TOWN = 'Villa Prisma'
CODE = 'DEMO-001'
COUNTRY = 'territorio ficticio'
VERSION = 1
WEIGHTS = {'activities': 30, 'exams': 35, 'projects': 25, 'participation': 10}
PERIODS = (('08:30','09:20'), ('09:20','10:10'), ('10:10','11:00'),
           ('11:30','12:20'), ('12:20','13:10'), ('13:10','14:00'))
STUDENTS_PER_GROUP = 4


def programs():
    plans = []
    for level in range(1, 5):
        subjects = ['Matemáticas', 'Lengua Castellana', 'Inglés', 'Geografía e Historia',
                    'Biología y Geología' if level < 3 else 'Física y Química',
                    'Educación Física' if level % 2 else 'Tecnología y Educación Plástica']
        plans.append((f'{level}.º ESO', 'ESO', ['A', 'B'], subjects))
    for level in (1, 2):
        plans.append((f'{level}.º Bachillerato · Ciencias y Tecnología', 'Bachillerato', ['CT'],
                      [f'Matemáticas {"I" if level == 1 else "II"}', 'Lengua Castellana', 'Inglés',
                       'Física', 'Química' if level == 1 else 'Biología', 'Tecnología e Ingeniería']))
        plans.append((f'{level}.º Bachillerato · Humanidades y Ciencias Sociales', 'Bachillerato', ['HCS'],
                      ['Matemáticas aplicadas', 'Lengua Castellana', 'Inglés', 'Filosofía',
                       'Historia de España', 'Economía y sociedad']))
    for name, stage, subjects in (
        ('Servicios digitales', 'FP · Grado Básico', ['Comunicación', 'Ciencias aplicadas', 'Equipos informáticos', 'Ofimática', 'Redes locales', 'Proyecto de aula']),
        ('Sistemas y redes', 'FP · Grado Medio', ['Sistemas Informáticos', 'Redes', 'Seguridad digital', 'Aplicaciones Web', 'Bases de Datos', 'Proyecto técnico']),
        ('Desarrollo de aplicaciones', 'FP · Grado Superior', ['Programación', 'Bases de Datos', 'Sistemas Informáticos', 'Entornos de Desarrollo', 'Aplicaciones Web', 'Proyecto de software']),
    ):
        for level in (1, 2):
            plans.append((f'{level}.º {name}', stage, ['A'], subjects))
    return plans


def teaching_text(subject, unit):
    if 'Matemáticas' in subject:
        text = ('Una función afín se escribe f(x)=ax+b. La pendiente a mide la variación por unidad y b es f(0). '
                'En f(x)=2x+3, al pasar de x=1 a x=2 el resultado cambia de 5 a 7. '
                'El modelo y sus unidades deben comprobarse en una tabla y una gráfica.')
    elif subject in ('Programación', 'Entornos de Desarrollo', 'Proyecto de software'):
        text = ('Un programa transforma entradas en salidas mediante instrucciones. Una función debe tener una responsabilidad clara. '
                'Comprueba los casos límite y valida los datos. Una prueba compara el resultado observado con el esperado. '
                'El control de versiones conserva cambios revisables.')
    elif subject == 'Bases de Datos':
        text = ('Una tabla almacena registros. La clave primaria identifica un registro y una clave foránea conecta dos tablas. '
                'Una transacción agrupa cambios que deben completarse conjuntamente. '
                'Una consulta debe filtrar el ámbito del usuario antes de devolver datos.')
    elif subject in ('Redes', 'Redes locales', 'Sistemas Informáticos', 'Equipos informáticos', 'Seguridad digital'):
        text = ('Una red conecta equipos mediante protocolos. Las direcciones identifican destinos y los servicios escuchan en puertos. '
                'El permiso mínimo reduce el acceso a lo necesario. Prueba primero el servicio local y después su conexión autorizada.')
    elif subject == 'Aplicaciones Web':
        text = ('Una aplicación web separa presentación, reglas y persistencia. HTML estructura, CSS presenta y el servidor valida permisos. '
                'Los formularios necesitan etiquetas, errores comprensibles y confirmaciones de guardado.')
    elif subject in ('Lengua Castellana', 'Comunicación', 'Inglés', 'Filosofía', 'Geografía e Historia', 'Historia de España', 'Economía y sociedad'):
        text = ('Organiza una explicación con una idea principal, evidencias y una conclusión. Distingue hechos de interpretaciones. '
                'Revisa el vocabulario, los conectores y la procedencia de las afirmaciones. '
                'En un relato, el narrador determina qué conoce el lector.')
    else:
        text = ('Formula una pregunta y registra las observaciones. Compara una variable cada vez y anota sus unidades. '
                'Describe el procedimiento para que otra persona pueda repetirlo. '
                'Una conclusión explica qué observaciones la sostienen y qué dudas permanecen.')
    return f'Tema {unit} de {subject}. {text}\n\nMaterial original ficticio de AXON para Nébula. Ejercita, explica y revisa un ejemplo propio.'


def original_document(db, settings, owner, title, content, *, subject_id=None, access='personal', source='Material original ficticio'):
    checksum = sha256(content.encode()).hexdigest()
    key = 'nebula-' + owner.id[:8] + '-' + sha256((title+content).encode()).hexdigest()[:32] + '.md'
    path = settings.data_dir / 'uploads' / key
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not path.exists():
        path.write_text(content, encoding='utf-8')
        path.chmod(0o600)
    doc = Document(center_id=owner.center_id, owner_id=owner.id, title=title[:180], filename=key,
                   storage_key=key, checksum=checksum, size=len(content.encode()), access=access,
                   subject_id=subject_id, status='validated', source=source)
    db.add(doc)
    db.flush()
    db.add(DocumentChunk(document_id=doc.id, ordinal=0, location='Material ficticio · fragmento 1', content=content))
    return doc


def populate(db, settings, center_id=None):
    """Add the full scenario once, only to a declared fictional center."""
    center = db.get(Center, center_id) if center_id else db.scalar(select(Center).where(Center.name == CENTER_NAME))
    if not center or not center.settings.get('fictional'):
        raise ValueError('La simulación necesita un centro marcado como ficticio')
    if center.settings.get('nebula_version') == VERSION:
        return counts(db, center)
    if db.scalar(select(LearningClass.id).where(LearningClass.center_id == center.id).limit(1)):
        raise ValueError('El centro contiene clases previas. Prepara una demostración nueva')
    year = db.scalar(select(AcademicYear).where(AcademicYear.center_id == center.id).limit(1))
    if not year:
        year = AcademicYear(center_id=center.id, name='Curso simulado')
        db.add(year)
        db.flush()
    people = {user.username: user for user in db.scalars(select(User).where(User.center_id == center.id))}
    admin = people.get('admin.demo')
    if not admin:
        raise ValueError('Prepara primero las cuentas ficticias con seed_demo')
    teachers = [people['profesor.demo'], people['profesora.demo']]
    for index in range(18):
        username = f'docente.nebula.{index+1:02d}'
        user = people.get(username)
        if not user:
            user = User(center_id=center.id, username=username, display_name=f'{("Elio", "Sira", "Nilo", "Lúa", "Aster", "Zia")[index%6]} {("Cenit", "Prisma", "Solsticio")[index//6]}',
                        role='teacher', active=True, is_demo=True, password_hash='', preferences={'theme':'dark'})
            db.add(user)
        teachers.append(user)
    db.flush()
    # Remove only the artificial compact fixture timetable, never an existing personal school.
    from sqlalchemy import delete
    from .models import Assignment, CalendarEvent
    compact_groups=select(Group.id).where(Group.center_id==center.id)
    db.execute(delete(Assignment).where(Assignment.group_id.in_(compact_groups)))
    db.execute(delete(CalendarEvent).where(CalendarEvent.center_id==center.id))
    db.execute(delete(Document).where(Document.center_id==center.id))
    db.execute(delete(Schedule).where(Schedule.center_id == center.id))
    db.execute(delete(Teaching).where(Teaching.group_id.in_(select(Group.id).where(Group.center_id == center.id))))
    db.execute(delete(Enrollment).where(Enrollment.group_id.in_(select(Group.id).where(Group.center_id == center.id))))
    subjects = {subject.name: subject for subject in db.scalars(select(Subject).where(Subject.center_id == center.id))}
    group_number = 0
    now = utcnow()
    monday = now.astimezone(MADRID).date() + timedelta(days=(7-now.astimezone(MADRID).weekday())%7 or 7)
    for course_name, stage, labels, names in programs():
        course = db.scalar(select(Course).where(Course.center_id == center.id, Course.name == course_name))
        if not course:
            course = Course(center_id=center.id, year_id=year.id, name=course_name, stage=stage)
            db.add(course)
            db.flush()
        else:
            course.stage = stage
        for label in labels:
            group_name = course_name + ' · ' + label
            group = Group(center_id=center.id, course_id=course.id, name=group_name[:100])
            room = Classroom(center_id=center.id, name=f'Aula Prisma {group_number+1:02d}')
            db.add_all([group, room])
            db.flush()
            learners = []
            for index in range(STUDENTS_PER_GROUP):
                # Three stable accounts let installers follow the same learner across the demonstration.
                key = ('alumno.demo','alumna.demo')[index] if group_number == 0 and index < 2 else ('alumno2.demo' if group_number == 1 and index == 0 else f'estudiante.nebula.{group_number+1:02d}.{index+1}')
                learner = people.get(key)
                if not learner:
                    learner = User(center_id=center.id, username=key,
                        display_name=f'{("Ari", "Vela", "Teo", "Uma")[index]} Nebulín {group_number+1:02d}',
                        role='student', active=True, is_demo=True, password_hash='', preferences={'theme':'dark'})
                    db.add(learner)
                    db.flush()
                db.add(Enrollment(user_id=learner.id, group_id=group.id))
                learners.append(learner)
            for slot, name in enumerate(names):
                teacher = teachers[(group_number + slot) % len(teachers)]
                subject = subjects.get(name)
                if not subject:
                    subject = Subject(center_id=center.id, name=name)
                    db.add(subject)
                    db.flush()
                    subjects[name] = subject
                db.add(Teaching(teacher_id=teacher.id, group_id=group.id, subject_id=subject.id))
                for weekday in range(5):
                    starts, ends = PERIODS[slot]
                    db.add(Schedule(center_id=center.id, group_id=group.id, subject_id=subject.id,
                                    teacher_id=teacher.id, classroom_id=room.id, weekday=weekday,
                                    starts=starts, ends=ends, source='Horario artificial de Nébula'))
                klass = LearningClass(center_id=center.id, group_id=group.id, subject_id=subject.id,
                    creator_id=teacher.id, name=f'{name} · {group.name}'[:140], color=('mint','sky','amber','orchid','coral')[slot%5],
                    description=f'{stage}. Aula ficticia con tres temas, actividades y evaluación de ejemplo.')
                db.add(klass)
                db.flush()
                db.add(ClassMember(class_id=klass.id, user_id=teacher.id, role='teacher'))
                db.add_all(ClassMember(class_id=klass.id, user_id=learner.id, role='student') for learner in learners)
                db.add(ClassPost(class_id=klass.id, author_id=teacher.id, title='Bienvenida al cuaderno de Nébula',
                    content=f'Revisa el tema 1 de {name}, consulta sus actividades y prepara tus dudas. Todo el contenido es ficticio.',
                    pinned=True, comments_open=True))
                topics = []
                for unit in (1,2,3):
                    topic = ClassTopic(class_id=klass.id, name=f'Tema {unit} · {name}'[:100])
                    db.add(topic)
                    db.flush()
                    doc = original_document(db, settings, teacher, f'Tema {unit} de {name} · {group.name}', teaching_text(name,unit), subject_id=subject.id)
                    db.add(ClassFile(class_id=klass.id, document_id=doc.id, topic_id=topic.id))
                    topics.append(topic)
                build_work(db, settings, klass, teacher, learners, topics, now, monday, slot)
                from .nebula_models import ClassEvaluation
                db.add(ClassEvaluation(class_id=klass.id, weights=WEIGHTS.copy()))
            from .nebula_models import GroupTutorship
            db.add(GroupTutorship(group_id=group.id, teacher_id=teachers[group_number % len(teachers)].id,
                                  classroom_id=room.id, office_hour='Miércoles 14:10 · tutoría ficticia'))
            group_number += 1
    # The small test fixture has no enrolments after replacing it with the complete simulation.
    unused = list(db.scalars(select(Group).where(Group.center_id == center.id,
        Group.id.not_in(select(Teaching.group_id)))))
    for group in unused:
        # Legacy task/event rows remain in the compact test fixture only. Full demo needs a coherent scope.
        from .models import Assignment, CalendarEvent
        db.execute(delete(Assignment).where(Assignment.group_id == group.id))
        db.execute(delete(CalendarEvent).where(CalendarEvent.group_id == group.id))
        db.delete(group)
    db.flush()
    for term in range(1,4):
        start = datetime.combine(monday + timedelta(days=21+term*7), time(15), MADRID)
        event = __import__('app.models', fromlist=['CalendarEvent']).CalendarEvent(
            center_id=center.id, owner_id=admin.id, title=f'Evaluación {term} · Nébula',
            description='Reunión de evaluación ficticia. Los periodos se pueden configurar.', kind='evaluation',
            visibility='center', starts_at=start, ends_at=start+timedelta(hours=1), source='Calendario artificial de Nébula')
        db.add(event)
    from .institutional import CURATED
    from .models import InstitutionalSource
    for key, entry in CURATED.items():
        document=original_document(db,settings,admin,entry['title'],entry['text'],access='center',source='Original ficticio de AXON')
        db.add(InstitutionalSource(center_id=center.id,document_id=document.id,source_url=entry['url'],
            category=entry['category'],checked_on=now.date().isoformat(),academic_year='simulado',
            verification='fictional_original',applicability='unconfirmed',authority='fictional',notes=entry['notes']))
    center.settings = {**center.settings, 'nebula_version':VERSION, 'fictional':True,
        'country':COUNTRY, 'code':CODE, 'break':{'starts':'11:00','ends':'11:30'},
        'organization':{'direction':admin.id,'studies':teachers[0].id,'secretary':teachers[1].id,
            'departments':[{'name':name,'coordinator_id':teachers[i].id} for i,name in enumerate(
                ('Ciencias y tecnología','Comunicación y sociedad','Formación Profesional'))]}}
    db.flush()
    return counts(db, center)


def build_work(db, settings, klass, teacher, learners, topics, now, monday, slot):
    team = ClassTeam(class_id=klass.id, name='Equipo Prisma')
    db.add(team)
    db.flush()
    db.add_all(ClassTeamMember(class_id=klass.id, team_id=team.id, student_id=learner.id) for learner in learners[:2])
    for index, kind in enumerate(('exercise','quiz','project','exam')):
        due = now + timedelta(days=index+2)
        exam_at = (datetime.combine(monday + timedelta(days=4), time(15), MADRID) + timedelta(minutes=65*slot)) if kind=='exam' else None
        if exam_at:
            due = exam_at + timedelta(hours=1)
        activity = ClassActivity(class_id=klass.id, topic_id=topics[index%3].id, creator_id=teacher.id,
            title={'exercise':'Explica y comprueba un ejemplo','quiz':'Cuestionario del primer tema',
                   'project':'Proyecto de investigación en equipo','exam':'Examen próximo de demostración'}[kind],
            instructions='Lee el material del tema. Responde con un ejemplo, describe tu procedimiento y justifica la conclusión.',
            kind=kind, delivery='team' if kind=='project' else 'individual', status='published',
            due_at=due, exam_at=exam_at, max_points=10,
            questions=[{'prompt':'¿Qué sostiene una conclusión?', 'options':['La evidencia registrada','Una suposición sin revisar']}] if kind=='quiz' else [])
        db.add(activity)
        db.flush()
        db.add(ClassRubric(activity_id=activity.id,criteria=[
            {'title':'Comprensión','description':'Relaciona el ejemplo con el tema.','points':4},
            {'title':'Procedimiento','description':'Muestra pasos comprobables.','points':4},
            {'title':'Comunicación','description':'Explica con claridad.','points':2}]))
        from .nebula_models import ClassSolution
        db.add(ClassSolution(activity_id=activity.id,content='Modelo de corrección ficticio: comprobar datos, explicar el método y contrastar la conclusión con el ejemplo.'))
        sync_activity_events(db,klass,teacher,activity)
        if kind=='exercise':
            for index, learner in enumerate(learners[:2]):
                submission = ClassSubmission(activity_id=activity.id, student_id=learner.id,
                    content='Ejemplo de respuesta ficticia con un procedimiento comprobado.',status='submitted', submitted_at=now-timedelta(hours=2))
                db.add(submission)
                db.flush()
                attachment=original_document(db,settings,learner,'Respuesta de práctica · '+klass.id[:8],
                    'Respuesta ficticia de la práctica '+klass.id+'. He descrito los datos y revisado el resultado.')
                db.add(ClassFile(class_id=klass.id,document_id=attachment.id,submission_id=submission.id))
                db.flush()
                save_revision(db,learner,submission,'submitted')
                if index==0:
                    submission.status='returned'
                    db.add(ClassGrade(submission_id=submission.id,reviewer_id=teacher.id,points=8,
                        feedback='Corrección ficticia: buen procedimiento. Explica mejor la conclusión.',criteria_scores=[3,3,2]))
                    db.flush()
                    save_revision(db,teacher,submission,'returned')
    for title,kind,delivery,person,team_id in (
        ('Proyecto corregido de ejemplo','project','team',None,team.id),
        ('Examen anterior corregido','exam','individual',learners[0],None),
        ('Participación en el debate','task','individual',learners[2],None),
    ):
        activity=ClassActivity(class_id=klass.id,topic_id=topics[0].id,creator_id=teacher.id,title=title,
            instructions='Evaluación ficticia de un trabajo anterior con justificación y comentarios.',kind=kind,
            delivery=delivery,status='closed',due_at=now-timedelta(days=3),max_points=10,
            exam_at=now-timedelta(days=4) if kind=='exam' else None)
        db.add(activity)
        db.flush()
        sync_activity_events(db,klass,teacher,activity)
        submission=ClassSubmission(activity_id=activity.id,student_id=person.id if person else None,
            team_id=team_id,content='Respuesta ficticia: el procedimiento se documentó y el resultado se revisó.',
            status='submitted',submitted_at=now-timedelta(days=4))
        db.add(submission)
        db.flush()
        save_revision(db,person or learners[0],submission,'submitted')
        submission.status='returned'
        db.add(ClassGrade(submission_id=submission.id,reviewer_id=teacher.id,points=7,
            feedback='Ejemplo de corrección docente: comprueba las unidades y refuerza la explicación.',criteria_scores=[]))
        db.flush()
        save_revision(db,teacher,submission,'returned')
    overdue = ClassActivity(class_id=klass.id, topic_id=topics[0].id, creator_id=teacher.id,
        title='Práctica con plazo vencido',instructions='Actividad ficticia que permite probar el cierre de plazo en el servidor.',
        kind='task',delivery='individual',status='published',due_at=now-timedelta(days=1),max_points=10)
    db.add(overdue)
    db.flush()
    sync_activity_events(db,klass,teacher,overdue)


def counts(db, center):
    return {'center':center.name, 'groups':db.scalar(select(func.count()).select_from(Group).where(Group.center_id==center.id)),
        'users':db.scalar(select(func.count()).select_from(User).where(User.center_id==center.id)),
        'classes':db.scalar(select(func.count()).select_from(LearningClass).where(LearningClass.center_id==center.id))}
