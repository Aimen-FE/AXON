"""Fictitious classroom exercises for the isolated local demonstration."""
from datetime import timedelta
from hashlib import sha256

from sqlalchemy import select

from .class_calendar import sync_activity_events
from .class_models import ClassActivity, ClassFile, ClassMember, ClassPost, ClassRubric, ClassTopic, LearningClass
from .db import new_id, utcnow
from .models import Document, DocumentChunk, Enrollment, Subject, Teaching, User


def seed_class_examples(db):
    users = {user.username: user for user in db.scalars(select(User).where(User.is_demo.is_(True)))}
    now = utcnow()
    options = (
        ('profesor.demo', 'alumno.demo', 'Matemáticas', 'Laboratorio de funciones', 'mint'),
        ('profesora.demo', 'alumno2.demo', 'Lengua Castellana', 'Taller de relatos', 'orchid'),
    )
    for teacher_name, learner_name, subject_name, title, color in options:
        teacher, learner = users[teacher_name], users[learner_name]
        group_id = db.scalar(select(Enrollment.group_id).where(Enrollment.user_id == learner.id))
        subject_id = db.scalar(select(Subject.id).join(Teaching, Teaching.subject_id == Subject.id)
                               .where(Teaching.teacher_id == teacher.id, Teaching.group_id == group_id,
                                      Subject.name == subject_name))
        room = LearningClass(center_id=teacher.center_id, creator_id=teacher.id, group_id=group_id,
                             subject_id=subject_id, name=title, color=color,
                             description='Clase con materiales y actividades de demostración.')
        db.add(room)
        db.flush()
        participants = [learner]
        if subject_name == 'Matemáticas':
            participants.append(users['alumna.demo'])
        db.add(ClassMember(class_id=room.id, user_id=teacher.id, role='teacher'))
        db.add_all(ClassMember(class_id=room.id, user_id=user.id, role='student') for user in participants)
        db.add(ClassPost(class_id=room.id, author_id=teacher.id, title='Empieza por el cuaderno de clase',
                         content='Consulta la guía del primer tema y prepara una pregunta para el próximo encuentro.',
                         pinned=True, comments_open=True))
        topic = ClassTopic(class_id=room.id, name='Primer cuaderno')
        db.add(topic)
        db.flush()
        if subject_name == 'Matemáticas':
            content = 'Una función afín tiene la forma f(x) = ax + b. La pendiente a indica cuánto cambia f(x) al aumentar x una unidad. La ordenada b es el valor f(0).'
            material = 'Guía breve de funciones afines'
            task_title = 'Dibuja e interpreta una recta'
            instructions = 'Representa f(x) = 2x + 3. Explica qué representan la pendiente y la ordenada.'
        else:
            content = 'El narrador es la voz que cuenta la historia. En primera persona participa o presencia los hechos. Un narrador externo puede tener información limitada o conocer pensamientos de varios personajes.'
            material = 'Guía breve de narradores'
            task_title = 'Escribe una escena con dos narradores'
            instructions = 'Cuenta la misma escena desde la primera persona y desde una tercera persona limitada.'
        document = Document(
            center_id=room.center_id, owner_id=teacher.id, subject_id=subject_id, title=material,
            filename='axon-material.md', storage_key='generated-' + new_id(),
            checksum=sha256(content.encode()).hexdigest(), size=len(content.encode()), source='Ejemplo ficticio de Clases',
        )
        db.add(document)
        db.flush()
        db.add(DocumentChunk(document_id=document.id, ordinal=0, location='Guía · fragmento 1', content=content))
        db.add(ClassFile(class_id=room.id, document_id=document.id, topic_id=topic.id))
        activity = ClassActivity(class_id=room.id, topic_id=topic.id, creator_id=teacher.id,
                                 title=task_title, instructions=instructions, kind='exercise',
                                 delivery='individual', status='published', due_at=now + timedelta(days=7), max_points=10)
        db.add(activity)
        db.flush()
        db.add(ClassRubric(activity_id=activity.id, criteria=[
            {'title': 'Comprensión', 'description': 'Aplica las ideas del primer cuaderno.', 'points': 6},
            {'title': 'Explicación', 'description': 'Justifica las decisiones con claridad.', 'points': 4},
        ]))
        sync_activity_events(db, room, teacher, activity)
