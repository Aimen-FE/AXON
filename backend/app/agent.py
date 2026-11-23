import re
import unicodedata
from datetime import datetime,timedelta,time,timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select
from .db import utcnow
from .models import Group,Subject,User,Enrollment,Teaching,BathroomPass
from .policy import group_ids
from .memory import MADRID,day_bounds


def norm(value):
    value=re.sub(r'(\d)\.?\s*[ºª°]',r'\1',value.lower())
    return ' '.join(re.sub(r'[^a-z0-9: /-]',' ', ''.join(c for c in unicodedata.normalize('NFD',value) if unicodedata.category(c)!='Mn')).split())


MONTHS={'enero':1,'febrero':2,'marzo':3,'abril':4,'mayo':5,'junio':6,'julio':7,'agosto':8,'septiembre':9,'octubre':10,'noviembre':11,'diciembre':12}


def parse_day(value):
    today=utcnow().astimezone(MADRID).date()
    s=re.sub(r'\b(?:de|por) la manana\b','',norm(value))
    if 'pasado manana' in s:return today+timedelta(days=2)
    if 'manana' in s:return today+timedelta(days=1)
    if 'hoy' in s:return today
    if 'ayer' in s:return today-timedelta(days=1)
    iso=re.search(r'\b(\d{4}-\d{2}-\d{2})\b',s)
    if iso:return datetime.strptime(iso.group(1),'%Y-%m-%d').date()
    numeric=re.search(r'\b(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\b',s)
    if numeric:return datetime(int(numeric.group(3) or today.year),int(numeric.group(2)),int(numeric.group(1))).date()
    named=re.search(r'\b(\d{1,2}) de ('+'|'.join(MONTHS)+r')(?: de (\d{4}))?\b',s)
    if named:return datetime(int(named.group(3) or today.year),MONTHS[named.group(2)],int(named.group(1))).date()
    weekdays={'lunes':0,'martes':1,'miercoles':2,'jueves':3,'viernes':4,'sabado':5,'domingo':6}
    for name,index in weekdays.items():
        if re.search(r'\b'+name+r'\b',s):
            offset=(index-today.weekday())%7
            if 'semana que viene' in s or 'proxima semana' in s:offset=7-today.weekday()+index
            elif 'proxim' in s and offset==0:offset=7
            return today+timedelta(days=offset)
    return None


def find_group(db,user,s):
    groups=list(db.scalars(select(Group).where(Group.id.in_(group_ids(db,user)))))
    hits=[g for g in groups if norm(g.name) in s or re.search(r'\b'+re.escape(norm(g.name).split()[0])+r'\s+'+re.escape(norm(g.name).split()[-1])+r'\b',s)]
    if len(hits)==1:return hits[0]
    if len(groups)==1 and not hits:return groups[0]
    return None


def plan(db,user,text,previous_user=None):
    """Intenciones reproducibles y cerradas; nunca extrae instrucciones de documentos."""
    from .learning_agent import plan_extension
    extended=plan_extension(db,user,text,previous_user)
    if extended is not None:return extended
    original=text
    s=norm(text)
    if previous_user and re.match(r'^(a las |el |para el |\d{1,2}:)',s) and any(w in norm(previous_user) for w in ('programa','examen','crea','recordatorio')):
        original=previous_user+' '+text
        s=norm(original)
    try: day=parse_day(original)
    except ValueError:return {'clarification':'La fecha no es válida. Indica día, mes y año.'}
    if not user.preferences.get('public_guest') and re.fullmatch(
        r'[ ¿?!.]*(?:(?:muestra|lista|ver|consulta|cuales son) )?(?:mis clases(?: de axon)?|que clases tengo)[ ¿?!.]*', s,
    ):
        return {'calls': [('query_classes', {})]}
    if not user.preferences.get('public_guest') and any(part in s for part in ('cuantas clases', 'pendientes de corregir', 'evaluaciones proximas', 'asignaciones del profesorado')):
        return {'calls':[('query_education',{})]}
    group=find_group(db,user,s)
    if re.search(r'\b(recuerda|recuerdame|guarda en (?:mi )?memoria|memoriza)\b',s) and not any(x in s for x in ('que recuerdas','que recuerde','que me recuerdes')):
        content=re.sub(r'^.*?\b(recuerda|recuérdame|memoriza|guarda en (?:mi )?memoria)\s*(que\s+)?','',original,flags=re.I).strip(' .:')
        if len(content)<2:return {'clarification':'Indica qué información personal quieres conservar.'}
        return {'calls':[('save_memory',{'content':content,'category':'reminder' if any(x in norm(content) for x in ('debo','repasar','tengo','pendiente')) else 'personal','event_at':datetime.combine(day,time(12),MADRID).isoformat() if day else None})]}
    if any(x in s for x in ('internet','busca en la web','busca online','buscar en la web')):
        query=re.sub(r'^.*?(?:internet|en la web|online)\s*[:,-]?\s*','',original,flags=re.I).strip()
        urls=re.findall(r'https?://[^\s<>]+',original)
        return {'calls':[('search_public',{'query':query[:250],'url':urls[0].rstrip('.,)') if urls else None,'consent':True})]}
    if any(x in s for x in ('sale al bano','salida al bano','registra la salida','salga al bano','vuelve del bano','regreso del bano','ha vuelto','registra el regreso')):
        if user.role=='student':return {'clarification':'Solo el profesorado y el personal autorizado pueden gestionar salidas.'}
        if not group:return {'clarification':'Indica el grupo autorizado para localizar al alumno sin ambigüedad.'}
        students=list(db.scalars(select(User).join(Enrollment).where(Enrollment.group_id==group.id,User.center_id==user.center_id,User.role=='student')))
        matches=[u for u in students if norm(u.display_name) in s]
        if matches:
            longest=max(len(u.display_name) for u in matches)
            matches=[u for u in matches if len(u.display_name)==longest]
        if len(matches)!=1:return {'clarification':'Indica el nombre de demostración exacto del alumno y su grupo; también puedes usar el formulario de Salidas.'}
        student=matches[0]
        if any(x in s for x in ('vuelve','regreso','ha vuelto')):
            active=db.scalar(select(BathroomPass).where(BathroomPass.student_id==student.id,BathroomPass.returned_at.is_(None)))
            return {'calls':[('return_bathroom',{'pass_id':active.id})]} if active else {'clarification':'Ese alumno no tiene una salida activa.'}
        return {'calls':[('register_bathroom',{'group_id':group.id,'student_id':student.id})]}
    create=any(x in s for x in ('programa','crear','crea ','publica','propon','pon un','anade','prepara un examen'))
    if create and any(x in s for x in ('examen','evento','recordatorio','reunion','tarea')):
        personal='recordatorio' in s
        task='tarea' in s and 'examen' not in s
        if not personal and user.role=='student':return {'clarification':'Tu perfil permite consultar los eventos académicos y crear recordatorios privados. La publicación corresponde al profesorado.'}
        if not personal and not group:return {'clarification':'Indica el grupo completo al que se dirige la propuesta.'}
        subjects=list(db.scalars(select(Subject).where(Subject.center_id==user.center_id)))
        matches=[x for x in subjects if norm(x.name) in s]
        subject=matches[0] if len(matches)==1 else None
        if not personal and not subject:return {'clarification':'Indica la asignatura de la propuesta.'}
        if not day:return {'clarification':'Indica una fecha válida, por ejemplo «19 de diciembre de 2026».'}
        hour=re.search(r'\b(?:a las?\s*)?(\d{1,2}):(\d{2})\b',s)
        if not hour:return {'clarification':'Indica la hora de inicio (por ejemplo, «a las 10:00»). No se ha creado ni publicado ningún evento.'}
        try: start=datetime.combine(day,time(int(hour.group(1)),int(hour.group(2))),MADRID)
        except ValueError:return {'clarification':'La hora no es válida. Utiliza el formato HH:MM.'}
        if start.astimezone(timezone.utc).astimezone(MADRID).replace(tzinfo=None)!=start.replace(tzinfo=None):
            return {'clarification':'Esa hora no existe en Europe/Madrid por el cambio de horario. Elige otra hora.'}
        if start.replace(fold=0).utcoffset()!=start.replace(fold=1).utcoffset():
            return {'clarification':'Esa hora es ambigua por el cambio de horario. Usa el formulario con un horario fuera del tramo del cambio.'}
        if task:
            return {'calls':[('create_assignment',{'title':'Tarea de '+subject.name,'description':original,'group_id':group.id,'subject_id':subject.id,'due_at':start.isoformat()})]}
        kind='reminder' if personal else 'exam' if 'examen' in s else 'meeting' if 'reunion' in s else 'event'
        title=('Recordatorio: '+original[:95]) if personal else ('Examen de ' if kind=='exam' else 'Evento de ')+subject.name
        return {'calls':[('publish_exam' if kind=='exam' else 'create_event',{'title':title,'description':original,'kind':kind,
            'group_id':None if personal else group.id,'subject_id':None if personal else subject.id,
            'visibility':'personal' if personal else 'group','starts_at':start.isoformat(),'ends_at':(start+timedelta(hours=1)).isoformat()})]}
    if any(x in s for x in ('informe','inconsistencias','revision diaria')) and user.role=='admin':
        return {'calls':[('prepare_report',{})]}
    if any(x in s for x in ('organiza','plan de estudio','organizar','planifica')) and any(x in s for x in ('estudi','semana')):
        return {'calls':[('query_exams',{}),('query_assignments',{})],'study':True}
    if any(x in s for x in ('documento','temario','apuntes','segun la guia','ecuaciones','protocolo','normativa')):
        return {'calls':[('search_documents',{'query':original[:300]})]}
    if any(x in s for x in ('recuerdas','memoria','dije','hablamos','preferencia','que paso','que ocurrio')):
        query=re.sub(r'\b(que|recuerdas|sobre|mi|mis|memoria|dije|hablamos|de|del|el|la|los|las|paso|ocurrio|te|he|dicho)\b',' ',s)
        query='' if day else query.strip()
        calls=[('search_memory',{'query':query[:300],'day':day.isoformat() if day else None})]
        if day:calls.append(('query_calendar',{'day':day.isoformat()}))
        return {'calls':calls}
    query={'query':s,'day':day.isoformat() if day else None}
    if 'examen' in s:return {'calls':[('query_exams',query)]}
    if any(x in s for x in ('tarea','entrega','deberes')):return {'calls':[('query_assignments',query)]}
    if any(x in s for x in ('horario','clase tengo','clases tengo')):return {'calls':[('query_schedule',query)]}
    if 'asignatura' in s:return {'calls':[('query_subjects',{})]}
    if any(x in s for x in ('fija ', 'prueba ', 'evaluacion', 'necesito publicar', 'quisiera programar')):return {}
    if any(x in s for x in ('calendario','evento','agenda')) or day:return {'calls':[('query_calendar',query)]}
    return {}


def format_results(db,user,results,study=False):
    lines=[]
    citations=[]
    for response in results:
        tool=response['tool']
        from .learning_tools import NAMES
        if tool in NAMES and response['status']!='pending_confirmation':
            from .learning_agent import format_extension
            extra,refs=format_extension(db,user,response);lines.append(extra);citations.extend(refs);continue
        value=response.get('result')
        if response['status']=='pending_confirmation':
            a=response['action']
            lines.append('He preparado una propuesta. Revisa los datos y pulsa «Confirmar» para aplicarla. Todavía no se ha publicado.')
            args=a['arguments']
            if args.get('title'):lines.append(args['title'])
            if args.get('starts_at'):
                start=datetime.fromisoformat(args['starts_at']).astimezone(MADRID)
                lines.append(start.strftime('%d/%m/%Y · %H:%M')+' · Europe/Madrid')
            if response.get('conflicts'):lines.append('Hay conflictos que debes resolver antes de confirmar: '+ '; '.join(c['title'] for c in response['conflicts']))
        elif tool=='save_memory':lines.append(('He guardado este recuerdo en tu sesión temporal: '+value['content']+'. Se eliminará al cerrar la sesión o caducar.') if user.preferences.get('public_guest') or user.preferences.get('demo_teacher') else ('He guardado este recuerdo privado: '+value['content']+'. Podrás recuperarlo en otra sesión.'))
        elif tool in ('query_exams','query_calendar'):
            lines.append('Exámenes publicados:' if tool=='query_exams' else 'Eventos confirmados:')
            lines.extend('• '+e['title']+' — '+datetime.fromisoformat(e['starts_at']).astimezone(MADRID).strftime('%d/%m/%Y a las %H:%M') for e in value[:15])
            if not value:lines.append('No hay registros confirmados en el período consultado.')
        elif tool=='query_assignments':
            lines.append('Tareas disponibles:')
            lines.extend('• '+e['title']+' — entrega '+datetime.fromisoformat(e['due_at']).astimezone(MADRID).strftime('%d/%m/%Y %H:%M')+(' · completada' if (e.get('submission') or {}).get('status') in ('submitted','completed','returned') else '') for e in value[:15])
            if not value:lines.append('No hay tareas registradas para tu grupo.')
        elif tool == 'query_education':
            lines.append(f"Clases autorizadas: {value['classes']}")
            if value['pending_reviews'] is not None:
                lines.append(f"Entregas pendientes de corregir: {value['pending_reviews']}")
            for event in value.get('upcoming_evaluations',[]):
                lines.append('• '+event['title']+' — '+event['starts_at'][:10])
            if value.get('upcoming_evaluations'):
                lines.append('Grupos incluidos en las evaluaciones de demostración: '+', '.join(value.get('evaluation_groups',[])))
            for assignment in value.get('teaching',[]):
                lines.append('• '+assignment['teacher']+' · '+assignment['group'])
        elif tool == 'query_classes':
            lines.append('Tus clases autorizadas: ' + ', '.join(row['name'] for row in value) if value
                         else 'Todavía no tienes clases autorizadas.')
        elif tool=='search_documents':
            if not value:lines.append('No encuentro fragmentos autorizados que respondan a la consulta. Puedes cargar el documento desde Documentos; no voy a inventar su contenido.')
            for i,c in enumerate(value[:3]):
                lines.append(f'[{i+1}] {c["title"]} · {c["location"]} · versión {c["version"]} · {c["status"]}\n{c["content"]}')
                citations.append({k:c[k] for k in ('document_id','title','location','version','status')})
        elif tool in ('search_memory','search_semantic_memory'):
            if not value['memories'] and not value['messages']:lines.append('No encuentro recuerdos o mensajes propios que coincidan con la consulta.')
            for m in value['memories'][:5]:lines.append('• Recuerdo personal: '+m['content'])
            for m in value['messages'][:3]:lines.append('• Conversación del '+datetime.fromisoformat(m['created_at']).astimezone(MADRID).strftime('%d/%m/%Y')+': '+m['content'][:300])
        elif tool=='query_schedule':
            subjects={x.id:x.name for x in db.scalars(select(Subject).where(Subject.center_id==user.center_id))}
            weekdays=['Lunes','Martes','Miércoles','Jueves','Viernes']
            lines.append('Horario confirmado:')
            for row in value[:30]:lines.append(f'• {weekdays[row["weekday"]]} {row["starts"]}–{row["ends"]}: {subjects.get(row["subject_id"],"Asignatura")}')
            if not value:lines.append('No hay sesiones oficiales registradas para tu grupo.')
        elif tool=='query_subjects':lines.append('Asignaturas disponibles: '+', '.join(x['name'] for x in value))
        elif tool=='register_bathroom':lines.append('Salida registrada correctamente. El regreso puede anotarse en Salidas o desde el chat.')
        elif tool=='return_bathroom':lines.append('Regreso registrado correctamente.')
        elif tool=='prepare_report':lines.append(f'Informe generado con {len(value["findings"])} hallazgos académicos. Puedes revisarlo en Informes; no contiene conversaciones privadas.')
        elif tool=='search_public':
            if not value.get('available'):lines.append(value['message'])
            elif value.get('kind')=='page':lines.append(value['title']+'\n'+value['excerpt'][:3000]+'\nFuente externa: '+value['url']+' · consultada '+value['checked_at'])
            else:lines.extend('• '+r['title']+' — '+r['excerpt']+'\n'+r['url'] for r in value.get('results',[]))
        elif tool=='research_sources':
            if not value.get('available'):lines.append(value.get('message','No se ha recuperado ninguna fuente pública. Revisa los fallos del informe.'))
            else:
                lines.append(value['report'])
                lines.append(value['comparison_scope'])
                if value['contradictions']:lines.append('Se han detectado posibles diferencias numéricas. Revisa las fuentes antes de concluir.')
                citations.extend({'title':s['title'],'url':s['url'],'checked_at':s['checked_at'],'status':'external'} for s in value['sources'])
        elif tool=='calculate_math':
            import json
            lines.append('Cálculo determinista ('+value['operation']+'):\n'+json.dumps(value['result'],ensure_ascii=False,indent=2))
        elif response['status']=='completed':lines.append('La operación se ha guardado correctamente.')
    if study:
        lines.append('Propuesta de estudio: dedica primero una sesión a la entrega más próxima; reparte el repaso de cada examen en sesiones breves los días anteriores. Indica qué bloques horarios prefieres para preparar recordatorios. No se ha guardado ningún plan automáticamente.')
    return '\n\n'.join(lines),citations
