import re
from datetime import datetime,time,timedelta,timezone
from sqlalchemy import select
from .models import Subject,AssessmentPolicy,LearnerProfile,LearnerSubject
from .academic_import import normalize
from .memory import MADRID


def resolve_subject(db,user,query):
    query=normalize(query)
    candidates=[]
    for subject in db.scalars(select(Subject).where(Subject.center_id==user.center_id)):
        name=normalize(subject.name);score=100+len(name) if name in query else 0
        aliases=[]
        if 'quimica' in name:aliases=['fisica','quimica','fisica y quimica']
        elif 'educacion fisica' in name:aliases=['educacion fisica']
        else:
            for prefix in ('matematic','filosof','tecnologia','ingles','digitaliz','lengua','atencion educativa'):
                if prefix in name:aliases.append(prefix)
        if 'ingles' in name and any(k in query for k in ('writing','listening','speaking','use of english','mediation','reading')):score=max(score,60)
        for alias in aliases:
            if alias in query:score=max(score,len(alias))
        if score:candidates.append((score,subject))
    return max(candidates,key=lambda pair:pair[0])[1] if candidates else None


def parse_hour(text):
    s=normalize(text)
    m=re.search(r'\b(\d{1,2}):(\d{2})\b',s)
    if m:return int(m[1]),int(m[2]),False
    m=re.search(r'\ba las?\s+(una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|\d{1,2})\b(?:\s+y\s+(media|cuarto))?',s)
    if not m:return None
    words={'una':1,'dos':2,'tres':3,'cuatro':4,'cinco':5,'seis':6,'siete':7,'ocho':8,'nueve':9,'diez':10,'once':11,'doce':12}
    h=words.get(m[1],int(m[1]) if m[1].isdigit() else 0);minute=30 if m[2]=='media' else 15 if m[2]=='cuarto' else 0
    ambiguous=not any(x in s for x in ('de la manana','de la tarde','de la noche')) and h<=7
    if ('de la tarde' in s or 'de la noche' in s or ambiguous) and h<12:h+=12
    return h,minute,ambiguous


def plan_extension(db,user,text,previous=None):
    from .agent import parse_day,norm
    s=norm(text);original=text
    if previous and re.match(r'^(a las |el |para el |\d{1,2}:)',s) and any(t in normalize(previous) for t in ('estudio','sesion','repaso')):
        original=previous+' '+text;s=norm(original)
    subject=resolve_subject(db,user,original)
    try:day=parse_day(original)
    except ValueError:return {'clarification':'La fecha no es válida. Indica una fecha completa.'}
    if re.search(r'\b(recuerda|memoriza|guarda en (?:mi )?memoria)\b',s):return None
    create=any(k in s for k in ('anade','agrega','apunta','programa','crea','pon una','pon un','guarda'))
    if create and any(k in s for k in ('sesion de estudio','repaso','evento personal','recordatorio','estudiar el')):
        if not day:return {'clarification':'Indica el día de la sesión de estudio.'}
        clock=parse_hour(original)
        if not clock:return {'clarification':'Indica la hora de la sesión de estudio (por ejemplo, a las 17:00).'}
        h,m,ambiguous=clock
        try:start=datetime.combine(day,time(h,m),MADRID)
        except ValueError:return {'clarification':'La hora indicada no es válida.'}
        if start.astimezone(timezone.utc).astimezone(MADRID).replace(tzinfo=None)!=start.replace(tzinfo=None) or start.replace(fold=0).utcoffset()!=start.replace(fold=1).utcoffset():return {'clarification':'La hora coincide con un cambio horario; elige una hora sin ambigüedad.'}
        return {'calls':[('create_event',{'title':'Estudio'+(' · '+subject.name if subject else ''),'description':original,'kind':'reminder','visibility':'personal','starts_at':start.isoformat(),'ends_at':(start+timedelta(minutes=45)).isoformat()})],
            'force_confirmation':ambiguous,'assumption':'He interpretado la hora como '+start.strftime('%H:%M')+' de Madrid; revisa la propuesta.' if ambiguous else None}
    if create and ('tarea personal' in s or user.role=='student' and 'tarea' in s):
        clock=parse_hour(original)
        if not day or not clock:return {'clarification':'Indica la fecha y hora de entrega para crear tu tarea personal.'}
        if clock[0]>23 or clock[1]>59:return {'clarification':'La hora no es válida.'}
        if clock[2]:return {'clarification':'Indica una hora inequívoca para la tarea, por ejemplo 17:00.'}
        start=datetime.combine(day,time(clock[0],clock[1]),MADRID)
        return {'calls':[('create_personal_task',{'title':original[:160],'description':original,'due_at':start.isoformat(),'subject_id':subject.id if subject else None})]}
    if 'examen' in s and any(k in s for k in ('que debo estudiar','que tengo que estudiar','preparar el','temario para')):return {'calls':[('get_study_context',{'day':day.isoformat() if day else None,'subject_id':subject.id if subject else None,'query':original[:600]})]}
    if any(k in s for k in ('plan de estudio','organiza','organizame','planifica')) and any(k in s for k in ('estudi','semana','plan')):
        return {'calls':[('create_study_plan',{'subject_id':subject.id if subject else None})]}
    if ('quiero estudiar' in s or 'vamos a estudiar' in s):
        if not subject:return {'clarification':'Indica la asignatura que quieres estudiar. Puedes elegirla en Estudio y planificación.'}
        return {'calls':[('query_knowledge',{'subject_id':subject.id,'query':'Temas y unidades disponibles para estudiar'})],'study_subject':subject.id}
    if any(k in s for k in ('que tenia pendiente','que tengo pendiente','mis pendientes','que debo repasar','que debia repasar')):
        return {'calls':[('get_pending',{})]}
    if any(k in s for k in ('que tengo','que me toca','que hay en mi agenda','mis clases','que clases')) and day:
        return {'calls':[('query_calendar',{'day':day.isoformat()}),('get_my_schedule',{'day':day.isoformat(),'subject_id':subject.id if subject else None}),('search_memory',{'day':day.isoformat()}),('query_assignments',{'day':day.isoformat()})]}
    if 'aula' in s or 'horario' in s or 'asignaturas' in s and day:
        return {'calls':[('get_my_schedule',{'day':day.isoformat() if day else None,'subject_id':subject.id if subject else None,'query':text[:500]})]}
    if any(k in s for k in ('profesor','profesora','docente','quien imparte')) and not any(k in s for k in ('evaluacion','criterio','dijo','recuperacion','nota')):
        return {'calls':[('get_teachers',{'subject_id':subject.id if subject else None})]}
    if any(k in s for k in ('vacaciones','festivos','calendario escolar','telefono del','correo del instituto','codigo de centro','direccion del instituto','informacion del centro','proyecto educativo','pec del','plan de acogida','plan de convivencia','normas del centro','normativa del instituto','propuesta curricular')):return {'calls':[('get_school_information',{'query':original[:600]})]}
    if 'asignaturas' in s:return {'calls':[('get_subjects',{})]}
    if subject and 'como se calcula' not in s and any(k in s for k in ('calcula','simula','que necesito sacar','que nota necesito')):
        policies=list(db.scalars(select(AssessmentPolicy).where(AssessmentPolicy.owner_id==user.id,AssessmentPolicy.subject_id==subject.id)))
        if len(policies)!=1:return {'clarification':'No hay una única regla de cálculo para esta asignatura. Selecciona su fuente en Calculadora de notas; no se supondrán porcentajes.'}
        policy=policies[0];values={}
        terms={'e1':['e1','primera evaluacion','primera'],'e2':['e2','segunda evaluacion','segunda'],'e3':['e3','tercera evaluacion','tercera']}
        labels={**terms,'exams':['examenes','pruebas escritas'],'activities':['actividades'],'practical':['practicas','trabajos practicos'],'participation':['participacion'],'projects':['proyectos'],'previous':['anterior'],'exam':['recuperacion']}
        labels.update({k:[k.replace('_',' ')] for k in policy.weights if k not in labels})
        for key,aliases in labels.items():
            for label in aliases:
                match=re.search(r'\b'+re.escape(label)+r'\s*(?::|=|es|de)?\s*(\d+(?:[.,]\d+)?)',s)
                if match:values[key]=match[1].replace(',','.');break
        target=any(k in s for k in ('necesito','necesaria','objetivo'))
        operation='target' if target else 'final' if any(k in values for k in terms) or 'final' in s else 'recovery' if 'previous' in values else 'term'
        unknown=None
        if target:
            candidates=list(terms) if policy.scheme=='philosophy' or any(k in values for k in terms) else list(policy.weights)
            absent=[k for k in candidates if k not in values];unknown=absent[0] if len(absent)==1 else 'e3' if policy.scheme=='philosophy' else candidates[0] if candidates else None
        return {'calls':[('calculate_grade',{'policy_id':policy.id,'operation':operation,'values':values,'unknown_component':unknown,'simulation':True})]}
    if any(k in s for k in ('criterio','evaluacion','calificacion','cuanto valen','ponderacion','porcentaje','cuanto vale','unidades','nota final','recuperacion','writing','de que curso','que dijo mi profesor','como se calcula')):
        return {'calls':[('query_knowledge',{'subject_id':subject.id if subject else None,'query':original[:600]})]}
    if any(k in s for k in ('notificaciones','avisos sin leer')):return {'calls':[('get_notifications',{})]}
    return None


def format_extension(db,user,response):
    from .agent import norm
    from .memory import MADRID
    name=response['tool'];value=response.get('result');citations=[];lines=[]
    subjects={s.id:s.name for s in db.scalars(select(Subject).where(Subject.center_id==user.center_id))}
    days=['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo']
    if name=='get_study_context':
        for exam in value['exams']:
            lines.append(exam['title']+' · '+datetime.fromisoformat(exam['starts_at']).astimezone(MADRID).strftime('%d/%m/%Y %H:%M'))
            lines.append('Temario publicado: '+exam['syllabus'] if exam.get('syllabus') else 'El examen no tiene un temario publicado; no se atribuyen unidades por suposición.')
            pending={p['unit_id']:p for p in value['progress'] if p['state']!='mastered'}
            units=[u for u in value['units'] if u['subject_id']==exam['subject_id'] and u['id'] in pending]
            if units:lines.append('Repaso personal sugerido por tu progreso (no es el temario confirmado del examen): '+', '.join(u['title'] for u in units[:5]))
        if not value['exams']:lines.append('No hay un examen confirmado en el período consultado. Añade un recordatorio privado si solo dispones de un aviso personal, o consulta al docente para confirmar temario y fecha.')
    elif name=='get_school_information':
        info=value['public_info'];calendar=value['calendar'];q=norm(value['question']);lines.append(value['name'])
        identity=value.get('identity',{}).get('identity',{})
        if 'codigo' in q and identity.get('center_code'):lines.append('Código de centro configurado: '+identity['center_code'])
        for fragment in value.get('institutional_fragments',[]):
            meta=fragment.get('institutional',{})
            lines.append(fragment['title']+' · '+fragment['location']+' · curso '+str(meta.get('academic_year') or 'sin fecha de curso')+' · aplicabilidad: '+meta.get('applicability','unconfirmed'))
            lines.append('Extracto documental para contrastar: '+fragment['content'][:900])
            lines.append('Origen: '+meta.get('source_url','')+' · consulta '+meta.get('checked_on',''))
            if meta.get('applicability')!='current':lines.append('Esta fuente no acredita una norma vigente para el curso actual.')
            citations.append({k:fragment[k] for k in ('document_id','title','location','status')})
        if any(k in q for k in ('vacacion','festiv','calendario')):
            if calendar:
                lines.append('Período lectivo documentado: '+calendar['starts']+' a '+calendar['ends'])
                lines.extend('• '+b['title']+': '+b['starts']+' a '+b['ends'] for b in calendar['breaks'])
                lines.append('Días no lectivos adicionales: '+', '.join(sorted(calendar['non_school_days'])))
                lines.append('Se aplican fines de semana. Los cambios particulares del centro requieren confirmación.')
            else:lines.append('Los extractos regionales deben leerse junto con sus modificaciones y el ámbito municipal. No hay un calendario particular del centro confirmado en tu perfil.' if any(f.get('institutional',{}).get('category')=='school_calendar' for f in value.get('institutional_fragments',[])) else 'No hay calendario escolar contrastado en tu perfil.')
        elif info:
            lines.extend('• '+label+': '+info[key] for key,label in [('code','Código'),('phone','Teléfono'),('email','Correo')] if key in info)
            if 'direccion' in q:lines.append('Dirección aportada por el titular, pendiente de contraste: '+info.get('postal_address_provided','no facilitada'))
        else:lines.append('No hay datos de contacto contrastados disponibles; no se completan por suposición.')
        for source in value['sources']:
            lines.append('Fuente: '+source['title']+' · '+(source['url'] or '')+' · consulta '+(str(source['checked_at'])[:10]))
            if source['document_id']:citations.append({'document_id':source['document_id'],'title':source['title'],'location':source['source_location'],'status':source['verification']})
    elif name=='get_my_schedule':
        for lesson in value['lessons']:
            title='Recreo' if lesson.get('is_break') else lesson.get('subject_name') or subjects.get(lesson.get('subject_id'),'Asignatura')
            teacher=lesson.get('teacher','');room=lesson.get('classroom','')
            lines.append(f'• {days[lesson["weekday"]]} {lesson["starts"]}–{lesson["ends"]}: {title}'+(f' · {teacher}' if teacher else '')+(f' · aula {room}' if room else ''))
        if not lines:lines.append('No hay clases confirmadas para el día o materia consultados.')
        for block in value.get('pending_blocks',[]):lines.append(f'• {days[block["weekday"]]} {block["starts"]}–{block["ends"]}: elección de materia pendiente; no se ha asignado una optativa por suposición.')
        if value['lessons']:lines.insert(0,'Horario disponible según la fuente aportada:')
        if value.get('calendar_note'):lines.append(value['calendar_note'])
        ids={r.get('source_id') for r in value['lessons']}
        from .models import KnowledgeSource
        for source in db.scalars(select(KnowledgeSource).where(KnowledgeSource.owner_id==user.id,KnowledgeSource.id.in_(ids))):
            if source.document_id:citations.append({'document_id':source.document_id,'title':source.title,'location':'Horario de grupo y selección personal','status':source.verification})
    elif name=='get_subjects':lines.append('Asignaturas seleccionadas: '+', '.join(s['name'] for s in value))
    elif name=='get_teachers':
        lines.extend('• '+subjects.get(t['subject_id'],'Asignatura')+': '+t['display_name']+(' · '+t['contact'] if t.get('contact') else '') for t in value)
        if not lines:lines.append('No hay un docente documentado para esta consulta.')
        from .models import KnowledgeSource
        for source in db.scalars(select(KnowledgeSource).where(KnowledgeSource.owner_id==user.id,KnowledgeSource.id.in_({t.get('source_id') for t in value}))):
            lines.append('Fuente: '+source.title+' · información aportada pendiente de validación institucional.')
            if source.document_id:citations.append({'document_id':source.document_id,'title':source.title,'location':source.source_location,'status':source.verification})
    elif name=='query_knowledge':
        q=norm(value['question']);source_map={s['id']:s for s in value['sources']}
        units=value['units'];policies=value['policies'];seen=set()
        if any(t in q for t in ('unidades','temas','estudiar')) and units:
            for unit in units:lines.append('• '+unit['code']+' · '+unit['title']+(f' · evaluación {unit["term"]}' if unit.get('term') else '')+(f' · {unit["sessions"]} sesiones previstas' if unit.get('sessions') else ''));seen.add(unit['source_id'])
            if 'estudiar' in q:lines.append('Elige una unidad y abre Estudio y planificación para trabajar ejercicios y guardar tu progreso personal.')
        elif any(t in q for t in ('de que curso','vigente','actualiz','antigu')):
            for source in value['sources']:lines.append(f'• {source["title"]}: curso {source["academic_year"] or "no identificado"}; {({'historical':'histórico','pending':'pendiente de validación'}.get(source['verification'],source['verification']))}.');seen.add(source['id'])
        else:
            labels={'exams':'Pruebas escritas','activities':'Actividades','practical':'Prácticas y trabajos','participation':'Observación y participación','projects':'Proyectos y tareas','listening':'Listening','speaking':'Speaking','reading':'Reading','writing':'Writing','mediation':'Mediation','use_of_english':'Use of English','culture':'Culture'}
            for p in policies:
                seen.add(p['source_id']);lines.append(subjects.get(p['subject_id'],'Asignatura')+':')
                weights=p['weights'];specific=next((key for key in weights if key in q),None)
                if 'writing' in q:specific='writing'
                if specific and specific in weights:lines.append(f'• {labels.get(specific,specific)}: {weights[specific]} %.')
                elif any(t in q for t in ('cuanto valen','examenes','pruebas escritas')) and 'exams' in weights:lines.append('• Pruebas escritas: '+weights['exams']+' %.')
                else:
                    lines.extend(f'• {labels.get(k,k)}: {w} %.' for k,w in weights.items())
                if p['final_weights']:
                    if p['scheme']=='philosophy':lines.append('Nota final = 0,20 × primera evaluación + 0,40 × segunda + 0,40 × tercera. Las restricciones completas de aprobación por media están pendientes de aportar.')
                    elif p['scheme']=='english':lines.append('Nota final = (evaluación 1 + 2 × evaluación 2 + 3 × evaluación 3) / 6. Se exige mínimo 1 por destreza y aprobar Use of English en cada evaluación.')
                    else:lines.append('Nota final: media aritmética de las tres evaluaciones después de recuperaciones.')
                if 'recuper' in q:
                    if p['conditions'].get('recovery_mean'):lines.append('Recuperación: media entre nota anterior y prueba, respetando un mínimo de 5 si aprueba la recuperación o se presenta a mejora. Consulta el original para las condiciones restantes.')
                    elif p['scheme']=='english':lines.append('Según este documento histórico, no hay examen de recuperación de cada evaluación. La extraordinaria tiene ponderaciones específicas distintas de las ordinarias.')
            if not policies and not units and value.get('fragments'):
                for f in value['fragments']:
                    lines.append(f['content']);citations.append({'document_id':f['document_id'],'title':f['title'],'location':f['location'],'status':f['status']})
            if not policies and not units and not value.get('fragments'):lines.append('No dispongo de reglas o unidades estructuradas autorizadas para esta consulta. No inventaré porcentajes ni temarios.')
            if not policies and units:lines.extend('• '+u['title'] for u in units);seen.update(u['source_id'] for u in units)
        for ident in seen:
            source=source_map.get(ident)
            if not source:continue
            tag='HISTÓRICO; no vigente automáticamente para '+source['applicable_year'] if source['verification']=='historical' else 'pendiente de validación institucional' if source['verification']=='pending' else source['verification']
            lines.append('Fuente: '+source['title']+' · curso '+(source['academic_year'] or 'no identificado')+' · '+tag+'.')
            if source['document_id']:citations.append({'document_id':source['document_id'],'title':source['title'],'location':source['source_location'] or 'Fuente académica','status':source['verification']})
    elif name=='create_personal_task':lines.append('Tarea personal guardada: '+value['title']+'. No se ha publicado para ningún grupo.')
    elif name=='get_notifications':
        lines.extend('• '+n['title']+': '+n['content'] for n in value if not n['read'])
        if not lines:lines.append('No tienes notificaciones pendientes de leer.')
    elif name=='get_pending':
        lines.extend('• Tarea: '+t['title'] for t in value['tasks'] if not t.get('submission'))
        lines.extend('• Tarea personal: '+t['title'] for t in value['personal_tasks'])
        lines.extend('• Recuerdo privado: '+m['content'] for m in value['memory']['memories'] if m['category']=='reminder' or any(t in norm(m['content']) for t in ('debo','repasar','pendiente','tengo')))
        if not lines:lines.append('No encuentro pendientes registrados en tus tareas o recuerdos privados.')
    elif name=='calculate_grade':
        lines.append('Simulación personal; no es una calificación oficial.')
        lines.extend(value.get('steps',[]))
        if value.get('grade') is not None:lines.append('Resultado orientativo: '+value['grade'])
        if value.get('required') is not None:lines.append('Nota necesaria: '+value['required']+(' · no alcanzable con un máximo de 10' if not value['reachable'] else ''))
        source=value.get('source')
        if source and source.get('document_id'):citations.append({'document_id':source['document_id'],'title':source['title'],'location':'Reglas de cálculo','status':source['verification']})
        lines.extend('Falta: '+x for x in value.get('missing',[]));lines.extend(value.get('warnings',[]))
    return '\n\n'.join(lines),citations
