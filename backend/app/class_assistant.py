"""Class-specific Ollama assistance. Only humans publish or assess work."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from .atlas import context as base100
from .auth import current_user, get_db
from .class_calendar import event_conflicts, room_events
from .class_models import ClassActivity, ClassTopic
from .class_policy import class_by_id, class_document_ids
from .class_schemas import AssistInput
from .classwork import my_submission
from .db import utcnow
from .documents import retrieve_documents
from .memory import MADRID, retrieve_memory
from .models import Document, User
from .providers import local_policy
from .relevance import attributed_citations

router = APIRouter(prefix='/classes', tags=['Asistente de clase'])

PURPOSES = {
    'explain': 'Explica el concepto de la pregunta paso a paso.',
    'review': 'Prepara un repaso con puntos y preguntas de autoevaluación.',
    'practice': 'Propón práctica guiada, con soluciones explicadas aparte.',
    'plan': 'Organiza un plan personal de estudio con pasos, estimaciones y fechas del contexto.',
    'activity': 'Propón un borrador de actividad con instrucciones, recursos y objetivo de aprendizaje.',
    'quiz': 'Prepara preguntas variadas y un solucionario separado para revisión docente.',
    'material': 'Prepara un borrador de material educativo con ejemplos.',
    'rubric': 'Propón criterios, descriptores observables y una distribución de puntos.',
    'summary': 'Resume los materiales pertinentes con citas cuando estén disponibles.',
    'unit': 'Esboza una unidad didáctica con objetivos, secuencia de sesiones y evaluación.',
    'level': 'Propón ejercicios en niveles inicial, intermedio y avanzado.',
    'feedback': 'Redacta comentarios de corrección accionables para revisión docente. No asignes una calificación.',
}
STAFF_MODES = {'activity', 'quiz', 'material', 'rubric', 'summary', 'conflicts', 'unit', 'level', 'feedback'}


def work_ahead(db, room, user):
    now = utcnow()
    items = db.scalars(select(ClassActivity).where(
        ClassActivity.class_id == room.id, ClassActivity.status == 'published', ClassActivity.due_at >= now,
    ).order_by(ClassActivity.due_at).limit(20))
    pending = []
    for activity in items:
        if user.role == 'student':
            submission, _ = my_submission(db, user, activity)
            if submission and submission.status in ('submitted', 'returned'):
                continue
        pending.append({'title': activity.title[:120], 'due_at': activity.due_at.astimezone(MADRID).isoformat()})
    return pending


@router.post('/{class_id}/assist')
async def ask(class_id: str, body: AssistInput, request: Request, user=Depends(current_user), db=Depends(get_db)):
    room = class_by_id(db, user, class_id, staff=body.mode in STAFF_MODES)
    tasks = work_ahead(db, room, user)
    if body.mode == 'pending':
        entries = [f"• {item['title']} — {item['due_at'][:10]} a las {item['due_at'][11:16]}" for item in tasks]
        return {'content': '\n'.join(entries) if entries else 'No tienes entregas pendientes con plazo abierto.',
                'citations': [], 'engine': 'structured', 'draft': False}
    if body.mode == 'conflicts':
        now = utcnow()
        events = [event for event in room_events(db, room) if event.status == 'published' and
                  event.kind != 'assignment' and now <= event.starts_at < now + timedelta(days=60)][:25]
        matches = [f'• {event.title}: {", ".join(overlaps)}' for event in events
                   if (overlaps := event_conflicts(db, user, event.starts_at, event.ends_at, event.id))]
        return {'content': '\n'.join(matches) if matches else 'No hay solapamientos en los eventos consultados para los próximos 60 días.',
                'citations': [], 'engine': 'structured', 'draft': False}
    documents = retrieve_documents(db, user, body.prompt[:300], limit=3, document_ids=class_document_ids(user, room.id))
    memories = retrieve_memory(db, user, body.prompt[:300], limit=2)['memories'] if body.use_memory else []
    topics = list(db.scalars(select(ClassTopic.name).where(ClassTopic.class_id == room.id).order_by(ClassTopic.name).limit(8)))
    settings = request.app.state.settings
    context = {
        'runtime_policy': local_policy(db, user, settings),
        'base100': {'identity': base100(db, user)['identity']},
        'documents': documents, 'memories': memories, 'class': {'name': room.name, 'topics': topics},
        'upcoming_work': tasks[:5], 'timezone': 'Europe/Madrid',
    }
    trusted_instruction = PURPOSES[body.mode]
    actor_id = user.id
    db.rollback()
    answer, engine = await request.app.state.ai.generate(
        [{'role': 'user', 'content': trusted_instruction + '\n\nPetición: ' + body.prompt}], context,
    )
    user = db.get(User, actor_id, populate_existing=True)
    if not user or not user.active:
        raise HTTPException(403, 'La cuenta ya no tiene acceso')
    class_by_id(db, user, class_id, staff=body.mode in STAFF_MODES)
    source_ids = {item['document_id'] for item in documents}
    if source_ids and set(db.scalars(select(Document.id).where(
        Document.id.in_(source_ids), Document.id.in_(class_document_ids(user, class_id)),
    ))) != source_ids:
        raise HTTPException(409, 'Los permisos de los materiales han cambiado. Vuelve a consultar')
    if settings.full_demo:
        from .teacher_demo import ensure
        ensure(db, user)
    # The model receives a bounded prefix of the selected fragments. Citations must refer to that prefix.
    sent = request.app.state.ai.bounded_context(context, 3500)['documents']
    if answer and engine == 'ollama':
        answer, citations = attributed_citations(answer, sent)
        if sent and not citations:
            # Label the sources supplied to the model, even if it omitted inline attribution.
            references = '\n'.join(f'• [fuente:{i}]' for i in range(1, len(sent) + 1))
            answer, citations = attributed_citations(answer + '\n\nMateriales consultados:\n' + references, sent)
    else:
        citations = []
        answer = {'simulated': 'La generación está desactivada en esta demostración.',
                  'local_busy': 'El modelo local está ocupado.', 'simulated_fallback': 'Ollama no está disponible.'}.get(
                      engine, 'El modelo local no ha devuelto una respuesta.')
        if documents:
            answer += '\n\nFragmentos de la clase:\n\n' + '\n\n'.join(
                document['content'][:550] + f' [fuente:{i}]' for i, document in enumerate(documents, 1)
            )
            answer, citations = attributed_citations(answer, documents)
    return {'content': answer, 'citations': citations, 'engine': engine, 'draft': body.mode in STAFF_MODES}
