"""Catálogo cerrado: el modelo propone argumentos, este módulo valida y autoriza."""
from dataclasses import dataclass
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ValidationError
from sqlalchemy import select, or_, and_, update
from . import schemas as S
from .learning_schemas import ResearchInput
from .auth import get_db, current_user
from .db import utcnow
from .models import (Group,CalendarEvent, Exam, Assignment, Schedule, Teaching, User, Center, Document,
                     ActionRequest, Approval, Memory, Subject, Notification)
from .policy import require_role, require_group, group_ids, event_filter, get_event, get_document, check_classroom, audit
from .serializers import record
from .education import events_for, assignments_for, notify_group, notify, bathroom_out, bathroom_return
from .memory import retrieve_memory, day_bounds

router = APIRouter(tags=['Herramientas y confirmaciones'])

@dataclass(frozen=True)
class Tool:
    description: str
    schema: type[BaseModel]
    roles: tuple[str, ...]
    level: int

ALL = ('student','teacher','admin')
STAFF = ('teacher','admin')
CATALOG = {
    'query_exams': Tool('Consultar exámenes publicados del ámbito autorizado', S.QueryArgs, ALL, 1),
    'query_calendar': Tool('Consultar calendario personal, de grupo y centro', S.QueryArgs, ALL, 1),
    'query_schedule': Tool('Consultar horarios confirmados', S.QueryArgs, ALL, 1),
    'query_assignments': Tool('Consultar tareas y fechas de entrega', S.QueryArgs, ALL, 1),
    'query_subjects': Tool('Consultar asignaturas autorizadas', S.EmptyArgs, ALL, 1),
    'search_memory': Tool('Buscar recuerdos y conversaciones propias por texto o fecha', S.QueryArgs, ALL, 1),
    'search_documents': Tool('Recuperar fragmentos de documentos autorizados con fuentes', S.QueryArgs, ALL, 1),
    'save_memory': Tool('Guardar información personal aportada voluntariamente', S.MemoryInput, ALL, 2),
    'create_event': Tool('Crear un recordatorio privado o proponer un evento académico', S.EventArgs, ALL, 3),
    'publish_exam': Tool('Proponer un examen; necesita confirmación y ausencia de conflictos', S.ExamArgs, STAFF, 3),
    'update_event': Tool('Proponer cambios de título o fechas de un evento', S.EventUpdate, ALL, 3),
    'cancel_event': Tool('Proponer la cancelación de un evento', S.EventCancel, ALL, 3),
    'create_assignment': Tool('Proponer una tarea para un grupo y asignatura autorizados', S.AssignmentArgs, STAFF, 3),
    'update_assignment': Tool('Modificar una tarea publicada mediante confirmación', S.AssignmentUpdate, STAFF, 3),
    'update_schedule': Tool('Modificar una sesión de horario mediante confirmación', S.ScheduleChange, STAFF, 3),
    'delete_schedule': Tool('Retirar una sesión de horario mediante confirmación', S.ScheduleDelete, STAFF, 3),
    'import_schedule': Tool('Proponer sesiones de horario validadas, desde formulario o CSV', S.ScheduleArgs, STAFF, 3),
    'register_bathroom': Tool('Registrar salida de un alumno de un grupo autorizado', S.BathroomArgs, STAFF, 2),
    'return_bathroom': Tool('Registrar regreso de una salida autorizada', S.ReturnArgs, STAFF, 2),
    'prepare_notification': Tool('Proponer comunicado de grupo o centro', S.NotificationArgs, STAFF, 3),
    'validate_document': Tool('Validar documentación institucional', S.ValidateDocumentArgs, ('admin',), 3),
    'prepare_report': Tool('Elaborar informe académico sin conversaciones privadas', S.EmptyArgs, ('admin',), 2),
    'search_public': Tool('Investigar una consulta pública o URL explícita, sin enviar contexto privado', ResearchInput, ALL, 1),
}

from . import learning_schemas as L
CATALOG.update({
    'query_education':Tool('Consultar número de clases, entregas por corregir, evaluaciones y asignaciones autorizadas',S.EmptyArgs,ALL,1),
    'query_classes':Tool('Consultar clases nativas propias o autorizadas en AXON',S.EmptyArgs,ALL,1),
    'get_study_context':Tool('Relacionar exámenes autorizados y temarios publicados con unidades y progreso propios',L.AcademicQuery,ALL,1),
    'get_school_information':Tool('Consultar los datos públicos contrastados del centro y el calendario escolar documentado',L.AcademicQuery,ALL,1),
    'get_my_schedule':Tool('Consultar horario personal y alternativas pendientes con su fuente',L.AcademicQuery,ALL,1),
    'get_subjects':Tool('Consultar únicamente las materias seleccionadas o autorizadas',S.EmptyArgs,ALL,1),
    'get_teachers':Tool('Consultar profesorado documentado del ámbito autorizado',L.AcademicQuery,ALL,1),
    'query_knowledge':Tool('Consultar criterios, unidades, reglas y vigencia de fuentes propias',L.AcademicQuery,ALL,1),
    'calculate_grade':Tool('Calcular una simulación decimal con reglas identificadas; nunca publicar una nota',L.CalculatorInput,ALL,1),
    'create_study_plan':Tool('Preparar un plan personal según disponibilidad; requiere confirmación para guardarlo',L.PlanInput,ALL,2),
    'save_study_plan':Tool('Guardar las sesiones de un plan propio tras confirmación y comprobación de conflictos',L.PlanConfirm,ALL,3),
    'get_notifications':Tool('Consultar notificaciones propias',S.EmptyArgs,ALL,1),
    'get_pending':Tool('Relacionar tareas y recuerdos privados pendientes entre conversaciones',S.EmptyArgs,ALL,1),
    'create_personal_task':Tool('Crear una tarea privada con fecha de entrega explícita',L.PersonalTaskInput,ALL,2),
})
from .atlas import CoreChange
from .advanced_schemas import MathInput,SemanticQuery,DossierInput,MaterialShare
CATALOG.update({
    'update_core':Tool('Actualizar o restaurar la identidad configurada del centro con historial y confirmación',CoreChange,('admin',),3),
    'calculate_math':Tool('Evaluar, simplificar, resolver, derivar, integrar, comprobar y obtener estadística con límites',MathInput,ALL,1),
    'search_semantic_memory':Tool('Buscar por significado solo recuerdos y mensajes propios ya indexados',SemanticQuery,ALL,1),
    'research_sources':Tool('Contrastar hasta tres páginas públicas con consentimiento y sin contexto privado',DossierInput,ALL,1),
    'share_material':Tool('Compartir un material propio revisado con un grupo autorizado; requiere confirmación',MaterialShare,STAFF,3),
})


def parse_tool(user, name, arguments):
    from .guest import is_guest,SAFE_TOOLS
    if is_guest(user) and name not in SAFE_TOOLS:raise HTTPException(403,'Los invitados solo pueden consultar y practicar; no modificar información institucional')
    spec = CATALOG.get(name)
    if not spec:
        raise HTTPException(404, 'Herramienta no disponible')
    require_role(user, *spec.roles)
    try:
        return spec.schema.model_validate(arguments)
    except ValidationError as exc:
        errors = [{'field':'.'.join(str(i) for i in e['loc']), 'message':e['msg']} for e in exc.errors()]
        raise HTTPException(422, {'message':'Revisa los datos de la propuesta', 'errors':errors})


def event_conflicts(db, user, args, exclude=None):
    if args.visibility == 'personal':
        scope = and_(CalendarEvent.visibility == 'personal', CalendarEvent.owner_id == user.id)
    else:
        checks = [CalendarEvent.owner_id == user.id]
        if args.group_id:
            checks.append(CalendarEvent.group_id == args.group_id)
        if args.classroom_id:
            checks.append(CalendarEvent.classroom_id == args.classroom_id)
        scope = or_(*checks)
    stmt = select(CalendarEvent).where(CalendarEvent.center_id == user.center_id,
        CalendarEvent.status == 'published', CalendarEvent.starts_at < args.ends_at,
        CalendarEvent.ends_at > args.starts_at, scope)
    if exclude:
        stmt = stmt.where(CalendarEvent.id != exclude)
    from .class_models import ClassEvent
    from .class_policy import class_event_ids
    stmt = stmt.where(or_(CalendarEvent.id.not_in(select(ClassEvent.event_id)),
                          CalendarEvent.id.in_(class_event_ids(user))))
    visible = set(db.scalars(select(CalendarEvent.id).where(event_filter(db, user))))
    return [{'id': e.id if e.id in visible else None, 'title':e.title if e.id in visible else 'Ocupación de recurso en otro ámbito',
             'starts_at':e.starts_at.isoformat(), 'ends_at':e.ends_at.isoformat()} for e in db.scalars(stmt)]


def event_args_for(obj, patch):
    data = {k:getattr(obj,k) for k in ('title','description','starts_at','ends_at','group_id','subject_id','classroom_id','visibility','kind')}
    data.update({k:v for k,v in patch.model_dump(exclude_none=True).items() if k not in ('event_id','version')})
    return S.EventArgs.model_validate(data)


def validate_event_scope(db, user, args):
    if args.visibility == 'group':
        require_group(db, user, args.group_id, args.subject_id, write=True)
    elif args.visibility == 'center':
        require_role(user, 'admin')
    elif args.subject_id:
        raise HTTPException(422, 'Los recordatorios personales no llevan asignatura institucional')
    check_classroom(db, user, args.classroom_id)
    if args.visibility == 'personal' and args.classroom_id:
        raise HTTPException(422, 'Un recordatorio personal no puede reservar aulas')


def validate_action(db, user, name, args):
    conflicts = []
    if name=='update_core':
        from .atlas import validate_change
        validate_change(db,user,args);return []
    if name=='share_material':
        from .materials import validate_share
        validate_share(db,user,args);return []
    if name=='save_study_plan':
        from .models import StudyPlan
        from .study import plan_conflicts
        plan=db.scalar(select(StudyPlan).where(StudyPlan.id==args.plan_id,StudyPlan.user_id==user.id))
        if not plan:raise HTTPException(404,'Plan privado no disponible')
        return plan_conflicts(db,user,plan)
    if name in ('publish_exam','create_event'):
        if name == 'publish_exam' and args.kind != 'exam':
            raise HTTPException(422, 'La propuesta debe ser de tipo examen')
        validate_event_scope(db, user, args)
        conflicts = event_conflicts(db, user, args)
    elif name in ('update_event','cancel_event'):
        obj = get_event(db, user, args.event_id, write=True)
        if obj.status != 'published' or obj.version != args.version:
            raise HTTPException(409, 'El evento ha cambiado; actualiza la propuesta')
        if name == 'update_event':
            merged = event_args_for(obj, args)
            validate_event_scope(db, user, merged)
            conflicts = event_conflicts(db, user, merged, obj.id)
    elif name == 'create_assignment':
        require_group(db, user, args.group_id, args.subject_id, write=True)
        for ident in args.material_ids:
            doc = get_document(db, user, ident)
            if not (doc.access in ('center','public') and doc.status in ('validated','official')) and not (doc.access == 'group' and doc.group_id == args.group_id):
                raise HTTPException(422, 'Los materiales deben estar disponibles para todo el grupo')
    elif name == 'update_assignment':
        obj=db.get(Assignment,args.assignment_id)
        if not obj or obj.center_id!=user.center_id:raise HTTPException(404,'Tarea no disponible')
        require_group(db,user,obj.group_id,obj.subject_id,write=True)
        if obj.updated_at!=args.expected_updated_at:raise HTTPException(409,'La tarea ha cambiado; actualiza la propuesta')
    elif name in ('import_schedule','update_schedule','delete_schedule'):
        exclude_id=None
        if name!='import_schedule':
            obj=db.get(Schedule,args.schedule_id)
            if not obj or obj.center_id!=user.center_id:raise HTTPException(404,'Sesión no disponible')
            require_group(db,user,obj.group_id,obj.subject_id,write=True)
            if user.role=='teacher' and obj.teacher_id!=user.id:raise HTTPException(403,'Solo puedes modificar tus propias sesiones')
            if obj.updated_at!=args.expected_updated_at:raise HTTPException(409,'La sesión ha cambiado; actualiza la propuesta')
            if name=='delete_schedule':return []
            entries=[S.ScheduleItem(group_id=obj.group_id,subject_id=obj.subject_id,teacher_id=obj.teacher_id,
                classroom_id=args.classroom_id,weekday=args.weekday,starts=args.starts,ends=args.ends)]
            exclude_id=obj.id
        else:entries=args.entries
        for i, row in enumerate(entries):
            require_group(db, user, row.group_id, row.subject_id, write=True)
            teacher = db.get(User, row.teacher_id)
            if not teacher or teacher.center_id != user.center_id or not teacher.active or teacher.role != 'teacher':
                raise HTTPException(422, 'Docente no disponible')
            if user.role == 'teacher' and row.teacher_id != user.id:
                raise HTTPException(403, 'Solo puedes preparar tu horario')
            if not db.scalar(select(Teaching.id).where(Teaching.teacher_id==row.teacher_id, Teaching.group_id==row.group_id, Teaching.subject_id==row.subject_id)):
                raise HTTPException(422, 'El docente no tiene esta asignatura asignada')
            check_classroom(db, user, row.classroom_id)
            existing = list(db.scalars(select(Schedule).where(Schedule.center_id==user.center_id, Schedule.weekday==row.weekday, Schedule.starts < row.ends, Schedule.ends > row.starts)))
            candidates = [*[r for r in existing if r.id!=exclude_id], *entries[:i]]
            for other in candidates:
                if other.weekday == row.weekday and other.starts < row.ends and other.ends > row.starts and (other.group_id==row.group_id or other.teacher_id==row.teacher_id or (row.classroom_id and other.classroom_id==row.classroom_id)):
                    conflicts.append({'title':f'Solapamiento de horario: día {row.weekday+1}, {row.starts}–{row.ends}'})
    elif name == 'prepare_notification':
        require_group(db, user, args.group_id, write=True) if args.group_id else require_role(user, 'admin')
    elif name == 'validate_document':
        doc = db.get(Document, args.document_id)
        if not doc or doc.center_id != user.center_id or doc.access == 'personal':
            raise HTTPException(404, 'Documento institucional no disponible')
    return conflicts


def execute_action(db, user, name, args):
    if name=='update_core':
        from .atlas import apply_change
        return apply_change(db,user,args)
    if name=='share_material':
        from .materials import share
        return share(db,user,args)
    if name=='save_study_plan':
        from .models import StudyPlan
        from .study import save_plan
        plan=db.scalar(select(StudyPlan).where(StudyPlan.id==args.plan_id,StudyPlan.user_id==user.id))
        if not plan:raise HTTPException(404,'Plan privado no disponible')
        return save_plan(db,user,plan)
    if name in ('create_event','publish_exam'):
        data = args.model_dump(exclude={'syllabus'})
        obj = CalendarEvent(center_id=user.center_id, owner_id=user.id, **data,
                            source='Recordatorio personal' if args.visibility=='personal' else 'Confirmado por docente' if user.role=='teacher' else 'Confirmado por administración')
        db.add(obj)
        db.flush()
        if obj.kind == 'exam':
            db.add(Exam(event_id=obj.id, syllabus=args.syllabus))
        if obj.group_id:
            notify_group(db, obj.group_id, obj.title, 'Nuevo evento académico confirmado', 'exam' if obj.kind=='exam' else 'event')
        elif obj.visibility == 'center':
            for uid in db.scalars(select(User.id).where(User.center_id==user.center_id, User.active.is_(True))):
                notify(db, uid, obj.title, 'Nuevo evento del centro', 'event')
        audit(db, user, name, obj)
        return record(obj)
    if name in ('update_event','cancel_event'):
        obj = get_event(db, user, args.event_id, write=True)
        if name == 'update_event':
            for k,v in args.model_dump(exclude={'event_id','version'}, exclude_none=True).items():
                setattr(obj,k,v)
        else:
            obj.status = 'cancelled'
        obj.version += 1
        if obj.group_id:
            notify_group(db, obj.group_id, obj.title, 'Evento actualizado' if name=='update_event' else 'Evento cancelado', 'exam' if obj.kind=='exam' else 'event')
        audit(db, user, name, obj)
        return record(obj)
    if name == 'create_assignment':
        obj = Assignment(center_id=user.center_id, creator_id=user.id, **args.model_dump())
        db.add(obj)
        db.flush()
        notify_group(db, obj.group_id, obj.title, 'Nueva tarea publicada', 'assignment')
        audit(db, user, name, obj)
        return record(obj)
    if name=='update_assignment':
        obj=db.get(Assignment,args.assignment_id)
        for k,v in args.model_dump(exclude={'assignment_id','expected_updated_at'},exclude_none=True).items():setattr(obj,k,v)
        db.flush();notify_group(db,obj.group_id,obj.title,'La tarea se ha actualizado. Revisa sus instrucciones y fecha de entrega.','assignment')
        audit(db,user,name,obj)
        return record(obj)
    if name in ('update_schedule','delete_schedule'):
        obj=db.get(Schedule,args.schedule_id)
        audit(db,user,name,obj)
        notify_group(db,obj.group_id,'Horario actualizado','Se ha modificado una sesión de horario' if name=='update_schedule' else 'Se ha retirado una sesión de horario','event')
        if name=='delete_schedule':
            ident=obj.id;db.delete(obj);return {'id':ident,'removed':True}
        for key in ('weekday','starts','ends','classroom_id'):setattr(obj,key,getattr(args,key))
        db.flush();return record(obj)
    if name == 'import_schedule':
        ids = []
        for row in args.entries:
            obj = Schedule(center_id=user.center_id, **row.model_dump())
            db.add(obj)
            db.flush()
            audit(db, user, name, obj)
            ids.append(obj.id)
        for gid in {r.group_id for r in args.entries}:
            notify_group(db, gid, 'Horario actualizado', 'Se han añadido sesiones confirmadas al horario', 'event')
        return {'ids':ids, 'count':len(ids)}
    if name == 'prepare_notification':
        if args.group_id:
            notify_group(db, args.group_id, args.title, args.content, 'announcement')
        else:
            for uid in db.scalars(select(User.id).where(User.center_id==user.center_id, User.active.is_(True))):
                notify(db, uid, args.title, args.content, 'announcement')
        return {'title':args.title, 'published':True}
    if name == 'validate_document':
        obj = db.get(Document, args.document_id)
        obj.status = args.status
        audit(db, user, name, obj)
        return record(obj, ('storage_key',))
    raise HTTPException(400, 'Acción no ejecutable')


def run_tool(db, user, name, arguments, settings,force_confirmation=False):
    args = parse_tool(user, name, arguments)
    from .extensions import TOOL_MODULE,require_module
    if name in TOOL_MODULE:require_module(db,user,TOOL_MODULE[name])
    if name=='calculate_math':
        from .mathematics import calculate_math
        return {'status':'completed','tool':name,'result':calculate_math(args)}
    if name=='search_semantic_memory':
        from .semantic import search_semantic
        return {'status':'completed','tool':name,'result':search_semantic(db,user,args,settings)}
    if name=='research_sources':
        from .research import research_sources
        result=research_sources(db,user,args)
        return {'status':'completed' if result.get('available') else 'unavailable','tool':name,'result':result}
    from .learning_tools import NAMES,run_learning_tool
    if name in NAMES:return run_learning_tool(db,user,name,args,settings)
    spec = CATALOG[name]
    if getattr(args,'day',None): day_bounds(args.day)
    if spec.level == 3:
        conflicts = validate_action(db, user, name, args)
        personal = name == 'create_event' and args.visibility == 'personal'
        if personal and user.preferences.get('automatic_personal_actions', True) and not conflicts and not force_confirmation:
            return {'status':'completed', 'tool':name, 'result':execute_action(db, user, name, args)}
        action = ActionRequest(center_id=user.center_id, user_id=user.id, tool=name,
                               arguments=args.model_dump(mode='json'), expires_at=utcnow()+timedelta(hours=24))
        db.add(action)
        db.flush()
        audit(db, user, 'action_proposed', action, {'tool':name})
        return {'status':'pending_confirmation', 'tool':name, 'action':record(action), 'conflicts':conflicts}
    if name == 'save_memory':
        obj = Memory(user_id=user.id, **args.model_dump())
        db.add(obj)
        db.flush()
        return {'status':'completed', 'tool':name, 'result':record(obj)}
    if name == 'register_bathroom':
        return {'status':'completed', 'tool':name, 'result':bathroom_out(db, user, args)}
    if name == 'return_bathroom':
        return {'status':'completed', 'tool':name, 'result':bathroom_return(db, user, args.pass_id)}
    if name == 'prepare_report':
        from .reports import build_report
        return {'status':'completed', 'tool':name, 'result':record(build_report(db, user.center_id, 'manual'))}
    if name == 'search_public':
        from .research import research
        result=research(db,user,args)
        return {'status':'completed' if result.get('available') else 'unavailable','tool':name,'result':result}
    if name == 'search_memory':
        result = retrieve_memory(db, user, args.query, args.day, limit=8)
    elif name == 'search_documents':
        from .documents import retrieve_documents
        result = retrieve_documents(db, user, args.query)
    elif name in ('query_exams','query_calendar'):
        from .agent import norm
        from .memory import MADRID
        from datetime import datetime,time
        query = norm(args.query)
        if args.day:
            start,end = day_bounds(args.day)
        elif 'semana' in query:
            today = utcnow().astimezone(MADRID).date()
            monday = today - timedelta(days=today.weekday())
            if 'proxima' in query or 'que viene' in query: monday += timedelta(days=7)
            start = datetime.combine(monday,time.min,MADRID)
            end = start + timedelta(days=7)
        else:
            start,end = utcnow(),utcnow()+timedelta(days=30)
        result = [e for e in events_for(db, user, 'exam' if name=='query_exams' else None, start, end) if e['status']=='published']
    elif name == 'query_education':
        from .education_settings import education_overview
        result=education_overview(db,user)
    elif name == 'query_classes':
        from .classes import list_classes
        result = [{key: room[key] for key in ('id', 'name', 'subject', 'group', 'archived')}
                  for room in list_classes(user, db)['classes']]
    elif name == 'query_assignments':
        result = assignments_for(db, user)
        from .agent import norm
        if not args.day and 'semana' in norm(args.query):
            from datetime import datetime, time
            from .memory import MADRID
            today=utcnow().astimezone(MADRID).date()
            monday=today-timedelta(days=today.weekday())
            if 'proxima' in norm(args.query) or 'que viene' in norm(args.query):
                monday+=timedelta(days=7)
            start=datetime.combine(monday,time.min,MADRID)
            end=start+timedelta(days=7)
            result=[row for row in result if start<=datetime.fromisoformat(row['due_at'])<end]
        if args.day:
            start,end=day_bounds(args.day)
            from datetime import datetime
            result=[r for r in result if start<=datetime.fromisoformat(r['due_at'])<end]
        if 'pendiente' in args.query.casefold() and user.role=='student':
            result=[r for r in result if r.get('class_status') != 'closed' and (not r.get('submission') or r['submission']['status'] == 'draft')]
    elif name == 'query_schedule':
        result = [record(s) for s in db.scalars(select(Schedule).where(Schedule.center_id==user.center_id, Schedule.group_id.in_(group_ids(db,user))).order_by(Schedule.weekday,Schedule.starts))]
        if args.day:
            from datetime import date
            weekday=date.fromisoformat(args.day).weekday()
            result=[r for r in result if r['weekday']==weekday]
    elif name == 'query_subjects':
        stmt = select(Subject).where(Subject.center_id==user.center_id)
        if user.role!='admin':
            stmt=stmt.where(Subject.id.in_(select(Teaching.subject_id).where(Teaching.group_id.in_(group_ids(db,user)))))
        result = [record(s) for s in db.scalars(stmt)]
    else:
        raise HTTPException(400, 'Consulta no disponible')
    if name in ('query_exams','query_calendar','query_assignments','query_schedule'):
        from .agent import norm
        query=norm(args.query)
        subjects=[s.id for s in db.scalars(select(Subject).where(Subject.center_id==user.center_id)) if norm(s.name) in query]
        groups=[g.id for g in db.scalars(select(Group).where(Group.id.in_(group_ids(db,user)))) if norm(g.name) in query]
        if subjects:result=[r for r in result if r.get('subject_id') in subjects]
        if groups:result=[r for r in result if r.get('group_id') in groups]
    return {'status':'completed','tool':name,'result':result}


@router.get('/tools')
def catalog(user=Depends(current_user)):
    return [{'name':name,'description':t.description,'arguments_schema':t.schema.model_json_schema(),
             'roles':t.roles,'confirmation_level':t.level} for name,t in CATALOG.items() if user.role in t.roles and (not user.preferences.get('public_guest') or name in __import__('app.guest',fromlist=['SAFE_TOOLS']).SAFE_TOOLS)]


@router.post('/tools/call')
def call(body: S.ToolCall, request: Request, user=Depends(current_user), db=Depends(get_db)):
    result = run_tool(db,user,body.tool,body.arguments,request.app.state.settings)
    db.commit()
    return result


@router.get('/actions')
def actions(user=Depends(current_user), db=Depends(get_db)):
    return [record(x) for x in db.scalars(select(ActionRequest).where(ActionRequest.user_id==user.id).order_by(ActionRequest.created_at.desc()).limit(100))]


@router.post('/actions/{action_id}/confirm')
def confirm(action_id: str, user=Depends(current_user), db=Depends(get_db)):
    obj=db.scalar(select(ActionRequest).where(ActionRequest.id==action_id,ActionRequest.user_id==user.id))
    if not obj:
        raise HTTPException(404,'Propuesta no disponible')
    if obj.status=='approved':
        return {'status':'approved','result':obj.result,'action':record(obj)}
    if obj.status!='pending':
        raise HTTPException(409,'Esta propuesta ya no está pendiente')
    if obj.expires_at <= utcnow():
        obj.status='expired'
        db.commit()
        raise HTTPException(409,'La propuesta ha caducado; crea una nueva')
    # Compare-and-swap acquires the write lock before rechecking conflicts in SQLite.
    changed=db.execute(update(ActionRequest).where(ActionRequest.id==obj.id,ActionRequest.status=='pending').values(status='executing')).rowcount
    if not changed:
        db.rollback()
        raise HTTPException(409,'La propuesta se está procesando')
    # Serialize academic changes per center on PostgreSQL as well as SQLite.
    if db.bind.dialect.name != 'sqlite':
        db.execute(select(Center.id).where(Center.id==user.center_id).with_for_update())
    args=parse_tool(user,obj.tool,obj.arguments)
    from .extensions import TOOL_MODULE,require_module
    if obj.tool in TOOL_MODULE:require_module(db,user,TOOL_MODULE[obj.tool])
    conflicts=validate_action(db,user,obj.tool,args)
    if conflicts:
        db.rollback()
        raise HTTPException(409,{'message':'Hay conflictos. Cambia la propuesta antes de publicar','conflicts':conflicts})
    result=execute_action(db,user,obj.tool,args)
    obj.status, obj.result='approved',result
    db.add(Approval(action_id=obj.id,approver_id=user.id,decision='approved'))
    audit(db,user,'action_confirmed',obj,{'tool':obj.tool})
    db.commit()
    return {'status':'approved','result':result,'action':record(obj)}


@router.post('/actions/{action_id}/reject')
def reject(action_id: str, user=Depends(current_user), db=Depends(get_db)):
    obj=db.scalar(select(ActionRequest).where(ActionRequest.id==action_id,ActionRequest.user_id==user.id))
    if not obj:
        raise HTTPException(404,'Propuesta no disponible')
    if obj.status!='pending':
        raise HTTPException(409,'Esta propuesta ya no está pendiente')
    obj.status='rejected'
    if obj.tool=='save_study_plan':
        from .models import StudyPlan
        plan=db.scalar(select(StudyPlan).where(StudyPlan.id==obj.arguments.get('plan_id'),StudyPlan.user_id==user.id))
        if plan and plan.status=='draft':plan.status='rejected'
    db.add(Approval(action_id=obj.id,approver_id=user.id,decision='rejected'))
    audit(db,user,'action_rejected',obj)
    db.commit()
    return record(obj)
