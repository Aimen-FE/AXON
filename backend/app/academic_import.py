"""Importadores auditables. Los documentos son datos y nunca instrucciones ejecutables."""
import hashlib,io,json,re,secrets
from datetime import timedelta
from pathlib import Path
from uuid import uuid4
from sqlalchemy import select
from fastapi import HTTPException
from pypdf import PdfReader
from .db import utcnow
from .models import (User,Center,AcademicYear,Course,Group,Subject,Enrollment,Document,DocumentChunk,
    AccountSetup,LearnerProfile,LearnerSubject,KnowledgeSource,AcademicTeacher,
    PersonalScheduleSlot,CourseUnit,EvaluationCriterion,AssessmentPolicy)
from .documents import extract,ALLOWED
from .auth import digest
from .serializers import record


def normalize(text):
    import unicodedata
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD',text.lower()) if not unicodedata.combining(c)).split())


def detected_year(text):
    match=re.search(r'\b(20\d{2})\s*[-–/]\s*(20\d{2})\b',text)
    return f'{match[1]}-{match[2]}' if match else None


def parse_schedule(raw):
    """Peñalara: geometric rows/columns, preserving all parallel alternatives."""
    reader=PdfReader(io.BytesIO(raw));page=reader.pages[0]
    if len(reader.pages)!=1:raise HTTPException(422,'El importador de horario espera una página de Peñalara')
    points=[]
    def visit(text,cm,tm,font,size):
        if text.strip():points.append({'x':float(tm[4]),'y':float(tm[5]),'text':text.strip()})
    page.extract_text(visitor_text=visit)
    codes=[p for p in points if re.fullmatch(r'[A-Z]{3}\d[A-Z0-9~]+',p['text'])]
    columns=sorted({round(p['x'],1) for p in codes})
    if len(columns)!=5:raise HTTPException(422,'No se han identificado cinco columnas lectivas; revisa manualmente el horario')
    times=sorted([p for p in points if p['x']<columns[0]-5 and re.fullmatch(r'\d{1,2}:\d{2}',p['text'])],key=lambda p:-p['y'])
    if len(times)!=14:raise HTTPException(422,'No se han identificado seis sesiones y un recreo; no se importará una cuadrícula supuesta')
    bands=[]
    for i in range(0,len(times),2):
        starts,ends=times[i:i+2]
        bands.append({'starts':starts['text'].zfill(5),'ends':ends['text'].zfill(5),'y':(starts['y']+ends['y'])/2})
    result=[]
    for code in codes:
        day=min(range(5),key=lambda i:abs(columns[i]-code['x']))
        band=min(bands,key=lambda b:abs(b['y']-code['y']))
        if abs(band['y']-code['y'])>45:raise HTTPException(422,'Hay una materia fuera de las franjas identificadas')
        teacher=next((p['text'] for p in points if abs(p['x']-code['x'])<2 and abs(p['y']-(code['y']-10))<2),'')
        room=next((p['text'] for p in points if p['x']>code['x']+40 and p['x']<code['x']+90 and abs(p['y']-(code['y']-10))<2),'')
        result.append({'weekday':day,'starts':band['starts'],'ends':band['ends'],'raw_code':code['text'],'teacher':teacher,'classroom':room,'is_break':False})
    breaks=[b for b in bands if b['ends']>'11:00' and b['starts']=='11:00']
    if not breaks:raise HTTPException(422,'No se ha identificado el recreo')
    for day in range(5):result.append({'weekday':day,'starts':breaks[0]['starts'],'ends':breaks[0]['ends'],'raw_code':'RECREO','teacher':'','classroom':'','is_break':True})
    return result


def parse_document(raw,suffix,kind):
    chunks=extract(raw,suffix);text='\n'.join(c[1] for c in chunks)
    # Non-overlapping text for parsers. The stored chunks deliberately overlap for retrieval.
    if suffix=='.pdf':
        reader=PdfReader(io.BytesIO(raw));text='\n'.join(p.extract_text(extraction_mode='layout') or '' for p in reader.pages)
    elif suffix=='.docx':
        from docx import Document as Word
        from docx.oxml.ns import qn
        doc=Word(io.BytesIO(raw))
        def tx(el):return ''.join(n.text or '' for n in el.iter(qn('w:t')) if not any(p.tag==qn('w:del') for p in n.iterancestors()))
        text='\n'.join(tx(p) for p in doc.element.body.iter(qn('w:p')))
    import unicodedata
    text='\n'.join(re.sub(r'[^\S\n]+',' ',line).strip() for line in unicodedata.normalize('NFKC',text).replace('\u200b','').splitlines())
    result={'year':detected_year(text),'units':[],'criteria':[],'weights':{},'final_weights':[],'conditions':{},'rules_text':text,'slots':[],'warnings':[]}
    if kind=='schedule':
        if suffix!='.pdf':raise HTTPException(422,'El horario debe ser PDF')
        result['slots']=parse_schedule(raw)
    elif kind=='physics':
        if suffix!='.docx':raise HTTPException(422,'Este importador de Física y Química espera DOCX')
        for table in doc.tables:
            for i,row in enumerate(table.rows):
                cells=[tx(c._tc).strip() for c in row.cells]
                if len(cells)>=4 and re.fullmatch(r'UD\d+',cells[0]):
                    result['units'].append({'code':cells[0],'title':cells[1],'term':int(re.search(r'\d',cells[2])[0]),'sessions':int(cells[3]),'criteria':[],'content':'','location':f'Tabla de secuenciación · fila {i+1}'})
        match=re.search(r'Nota de evaluación:(.*?)Recuperación o mejora',text,re.S|re.I)
        section=match[1] if match else ''
        for key,pattern in [('practical',r'prácticas.{0,100}?(\d+)\s*%'),('activities',r'actividades.{0,100}?(\d+)\s*%'),('exams',r'pruebas escritas.{0,50}?(\d+)\s*%')]:
            m=re.search(pattern,section,re.I|re.S)
            if m:result['weights'][key]=m[1]
        result['final_weights']=['1','1','1']
        result['conditions']={'recovery_mean':True,'recovery_pass_floor':'5','failed_terms_limit':2,'minimum_failed_term':'3.5','term_rounding':'truncate' if 'truncando' in text else None,
            'final_rounding':'half_up_except_fail' if '0,5' in text and '4,99' in text else None,'extraordinary_weight':'100','third_term_recovery_note':'Sin prueba específica si hay otras evaluaciones suspensas; incluida en recuperación final ordinaria.'}
        if len(result['units'])!=13:result['warnings'].append('No se han detectado las trece unidades esperadas; revisa la extracción')
    elif kind=='technology':
        header=text.split('Distribución de Criterios')[0]
        matches=list(re.finditer(r'U\.\s*DID[ÁA]CTICA\s*(\d+)\.\s*(.*?)\.?\s*\(\s*(\d+)\s*SESIONES\s*\)',header,re.I|re.S))
        for m in matches:
            before=header[:m.start()];terms=re.findall(r'([123])\s*[ºªo]?\s*EVALUACI[ÓO]N',before,re.I)
            code='UD'+m[1]
            blocks=re.split(r'UNIDAD DID[ÁA]CTICA\s*'+m[1]+r'\.',text,flags=re.I)
            content=re.split(r'UNIDAD DID[ÁA]CTICA\s*\d+\.',blocks[-1],flags=re.I)[0] if len(blocks)>1 else ''
            competence=content.split('COMPETENCIAS ESPECÍFICAS Y CRITERIOS DE EVALUACIÓN')[-1].split('CONEXIÓN CON')[0]
            criteria=sorted(set(re.findall(r'\b[1-9]\.[1-9]\b',competence)))
            result['units'].append({'code':code,'title':' '.join(m[2].split()).strip(' .'),'term':int(terms[-1]) if terms else None,'sessions':int(m[3]),'criteria':criteria,'content':content.strip(),'location':'Secuenciación, página 1 · '+code})
        sections=[('participation','Observación y Participación Activa en Clase'),('projects','Proyectos y Tareas Prácticas'),('exams','Pruebas Escritas')]
        all_criteria={}
        for i,(key,label) in enumerate(sections):
            start=text.find(label);end=text.find(sections[i+1][1],start+len(label)) if i<2 else text.find('Sistema de Calificación Global',start)
            block=text[start:end if end>=0 else len(text)] if start>=0 else ''
            weight=re.search(r'\((\d+)\s*%\s*de la nota total\)',block,re.I)
            if weight:result['weights'][key]=weight[1]
            for criterion in re.finditer(r'(?m)^\s*(\d\.\d)\s*\(([\d,.]+)\s*%\):\s*(.*?)(?=\n\s*\d\.\d\s*\(|\Z)',block,re.S):
                code=criterion[1];item=all_criteria.setdefault(code,{'code':code,'competence':code.split('.')[0],'content':' '.join(criterion[3].split()),'instruments':[]})
                item['instruments'].append({'instrument':key,'weight':criterion[2].replace(',','.')})
        for unit in result['units']:
            for code in unit['criteria']:all_criteria.setdefault(code,{'code':code,'competence':code.split('.')[0],'content':'Criterio citado en la unidad; texto íntegro no desglosado en la fuente.','instruments':[]})
        result['criteria']=list(all_criteria.values());result['final_weights']=['1','1','1']
        result['conditions']={'recovery_mean':True,'recovery_pass_floor':'5','failed_terms_limit':2,'minimum_failed_term':'3.5','rounding':'integer_unspecified','extraordinary_weight':'100'}
        if len(result['units'])!=6:result['warnings'].append('No se han detectado las seis unidades esperadas')
    elif kind=='english':
        ordinary=text.split('EVALUACIÓN DE LA ASIGNATURA:')[0]
        for label,value in re.findall(r'(?m)^\s*(LISTENING|SPEAKING|READING|WRITING|MEDIATION|USE OF ENGLISH|CULTURE)\s+(\d+)\s*%',ordinary):
            result['weights'][label.lower().replace(' ','_')]=value
        result['final_weights']=['1','2','3']
        extra=text.split('El examen de la prueba extraordinaria')[-1]
        extra_weights={k.lower().replace(' ','_'):v for k,v in re.findall(r'(?m)^\s*(LISTENING|SPEAKING|READING|WRITING|MEDIATION|USE OF ENGLISH|CULTURE)\s+(\d+)\s*%',extra)}
        result['conditions']={'minimum_skill':'1','minimum_skill_cap':'4','tests_per_skill':'90','work_per_skill':'10','rounding_threshold':'0.75','use_of_english_pass_each_term':True,'ordinary_recovery_exam':False,'absence_loss_threshold_percent':'30','extraordinary_weights':extra_weights}
        for code in sorted(set(re.findall(r'(?m)^\s*([1-6]\.[1-4])',text))):
            result['criteria'].append({'code':code,'competence':code.split('.')[0],'content':'Consultar texto íntegro y competencia en el documento original.','instruments':[]})
    if kind in ('physics','technology','english') and (not result['weights'] or sum(float(v) for v in result['weights'].values())!=100):
        result['warnings'].append('Ponderaciones incompletas: la calculadora no suplirá porcentajes ausentes')
    return result


def create_source_from_document(db,user,document,kind,applicable_year,academic_year=None,settings=None):
    if document.owner_id!=user.id:raise HTTPException(403,'La importación estructurada requiere un documento de tu propiedad')
    existing=db.scalar(select(KnowledgeSource).where(KnowledgeSource.owner_id==user.id,KnowledgeSource.document_id==document.id))
    if existing:return existing,{'already_imported':True}
    raw=(settings.data_dir/'uploads'/document.storage_key).read_bytes()
    parsed=parse_document(raw,Path(document.filename).suffix.lower(),kind)
    year=parsed['year'] or academic_year
    warnings=list(parsed['warnings'])
    if not year:warnings.append('El documento no identifica curso académico; su aplicación actual está pendiente de confirmación')
    if parsed['year'] and academic_year and parsed['year']!=academic_year:warnings.append('El curso declarado difiere del documento; se conserva el curso indicado por la fuente')
    historical=bool(year and year!=applicable_year)
    if historical:warnings.append(f'Documento de {year}; no vigente automáticamente para {applicable_year}')
    source=KnowledgeSource(owner_id=user.id,document_id=document.id,subject_id=document.subject_id,title=document.title,kind=kind,
        academic_year=year,applicable_year=applicable_year,verification='historical' if historical else 'pending',checked_at=utcnow(),warnings=warnings,
        source_location='Documento aportado por su titular; pendiente de validación institucional')
    db.add(source);db.flush()
    if document.subject_id:
        for unit in parsed['units']:db.add(CourseUnit(owner_id=user.id,subject_id=document.subject_id,source_id=source.id,**unit))
        for criterion in parsed['criteria']:db.add(EvaluationCriterion(owner_id=user.id,subject_id=document.subject_id,source_id=source.id,**criterion))
        if kind in ('physics','technology','english'):
            db.add(AssessmentPolicy(owner_id=user.id,subject_id=document.subject_id,source_id=source.id,scheme=kind,weights=parsed['weights'],final_weights=parsed['final_weights'],conditions=parsed['conditions'],rules_text=parsed['rules_text']))
    if parsed['slots']:
        profile=db.scalar(select(LearnerProfile).where(LearnerProfile.user_id==user.id))
        if not profile:raise HTTPException(422,'Configura tu perfil académico antes de importar el horario')
        by_code={normalize(s.name):s for s in db.scalars(select(Subject).where(Subject.center_id==user.center_id))}
        # Mapping is a personal declaration, never guessed from a language model.
        code_map=profile.preferences.get('schedule_code_map',{})
        if not isinstance(code_map,dict):code_map={}
        for row in parsed['slots']:
            prefix=row['raw_code'][:3];name=code_map.get(prefix)
            subject=by_code.get(normalize(name)) if name else None
            if not row['is_break'] and not subject:
                label=f'{prefix} · opción por confirmar'
                subject=by_code.get(normalize(label))
                if not subject:
                    subject=Subject(center_id=user.center_id,name=label);db.add(subject);db.flush();by_code[normalize(label)]=subject
            db.add(PersonalScheduleSlot(owner_id=user.id,source_id=source.id,group_id=profile.group_id,subject_id=subject.id if subject else None,**row))
            if subject and row['teacher'] and not db.scalar(select(AcademicTeacher.id).where(AcademicTeacher.owner_id==user.id,AcademicTeacher.source_id==source.id,AcademicTeacher.subject_id==subject.id,AcademicTeacher.display_name==row['teacher'])):
                db.add(AcademicTeacher(owner_id=user.id,source_id=source.id,subject_id=subject.id,display_name=row['teacher']));db.flush()
    return source,{'units':len(parsed['units']),'criteria':len(parsed['criteria']),'slots':len(parsed['slots']),'warnings':warnings}


def store_document(db,user,path,title,subject_id,settings,content=None):
    filename=Path(path).name;raw=content.encode() if content is not None else Path(path).read_bytes()
    if not raw or len(raw)>settings.max_upload:raise ValueError('Documento vacío o de más de 10 MB')
    suffix=Path(filename).suffix.lower()
    if suffix not in ALLOWED:raise ValueError('Formato no admitido')
    checksum=hashlib.sha256(raw).hexdigest()
    existing=db.scalar(select(Document).where(Document.owner_id==user.id,Document.checksum==checksum,Document.subject_id==subject_id))
    if existing:return existing
    chunks=extract(raw,suffix);key=uuid4().hex+suffix
    uploads=settings.data_dir/'uploads';uploads.mkdir(parents=True,exist_ok=True,mode=0o700)
    target=uploads/key;target.write_bytes(raw);target.chmod(0o600)
    document=Document(center_id=user.center_id,owner_id=user.id,subject_id=subject_id,title=title,filename=filename,storage_key=key,checksum=checksum,access='personal',source='Aportado por el titular · pendiente de validación institucional',status='provisional',size=len(raw))
    db.add(document);db.flush()
    for i,(location,value) in enumerate(chunks):db.add(DocumentChunk(document_id=document.id,ordinal=i,location=location,content=value))
    return document


def provision_bundle(db,settings,bundle):
    """Local CLI only. Personal names/files come from a private manifest, never source code."""
    username=bundle['username'].lower();user=db.scalar(select(User).where(User.username==username))
    if user and (user.is_demo or user.role!='student'):raise ValueError('El identificador pertenece a una cuenta incompatible')
    if not user:
        center=Center(name=bundle['center'],town=bundle.get('town','Localidad sin indicar'),settings={'private_workspace':True,'automation_enabled':False,'bathroom_retention_days':14})
        db.add(center);db.flush()
        year=AcademicYear(center_id=center.id,name=bundle['academic_year']);db.add(year);db.flush()
        course=Course(center_id=center.id,year_id=year.id,name=bundle['course'],stage='Bachillerato');db.add(course);db.flush()
        group=Group(center_id=center.id,course_id=course.id,name=bundle['group']);db.add(group);db.flush()
        user=User(center_id=center.id,username=username,display_name=bundle['name'],role='student',password_hash='',active=False,is_demo=False,preferences={'theme':'dark','notifications':{},'automatic_personal_actions':True})
        db.add(user);db.flush();db.add(Enrollment(user_id=user.id,group_id=group.id))
        preferences=dict(bundle.get('preferences',{}),schedule_code_map=bundle.get('schedule_code_map',{}))
        db.add(LearnerProfile(user_id=user.id,group_id=group.id,year_id=year.id,program=bundle['course'],preferences=preferences))
        db.flush()
    subjects={s.name:s for s in db.scalars(select(Subject).where(Subject.center_id==user.center_id))}
    for name in bundle['subjects']+list(bundle.get('additional_subjects',[])):
        if name not in subjects:
            subjects[name]=Subject(center_id=user.center_id,name=name);db.add(subjects[name]);db.flush()
        if name in bundle['subjects'] and not db.scalar(select(LearnerSubject.id).where(LearnerSubject.user_id==user.id,LearnerSubject.subject_id==subjects[name].id)):
            db.add(LearnerSubject(user_id=user.id,subject_id=subjects[name].id,active=True))
    db.flush();results=[]
    for entry in bundle.get('documents',[]):
        subject=subjects.get(entry.get('subject'))
        document=store_document(db,user,entry['path'],entry.get('title',Path(entry['path']).stem),subject.id if subject else None,settings)
        source,counts=create_source_from_document(db,user,document,entry['kind'],bundle['academic_year'],entry.get('academic_year'),settings)
        results.append({'source_id':source.id,**counts})
    for entry in bundle.get('manual',[]):
        subject=subjects[entry['subject']]
        document=store_document(db,user,entry['kind']+'.md',entry['title'],subject.id,settings,content=entry['text'])
        source,counts=create_source_from_document(db,user,document,'general',bundle['academic_year'],entry.get('academic_year'),settings)
        if entry.get('policy') and not db.scalar(select(AssessmentPolicy.id).where(AssessmentPolicy.source_id==source.id)):
            policy=entry['policy'];db.add(AssessmentPolicy(owner_id=user.id,subject_id=subject.id,source_id=source.id,scheme=entry['kind'],weights=policy.get('weights',{}),final_weights=policy.get('final_weights',[]),conditions=policy.get('conditions',{}),rules_text=entry['text']))
        for criterion in entry.get('criteria',[]):
            if not db.scalar(select(EvaluationCriterion.id).where(EvaluationCriterion.source_id==source.id,EvaluationCriterion.code==criterion['code'])):
                db.add(EvaluationCriterion(owner_id=user.id,subject_id=subject.id,source_id=source.id,instruments=[],content='',**criterion))
        if entry.get('teacher'):
            teacher=entry['teacher'];existing=db.scalar(select(AcademicTeacher).where(AcademicTeacher.owner_id==user.id,AcademicTeacher.source_id==source.id,AcademicTeacher.subject_id==subject.id))
            if not existing:db.add(AcademicTeacher(owner_id=user.id,source_id=source.id,subject_id=subject.id,display_name=teacher['name'],contact=teacher.get('contact')))
        results.append({'source_id':source.id,**counts})
    for entry in bundle.get('public_sources',[]):
        document=store_document(db,user,entry['kind']+'.md',entry['title'],None,settings,content=entry['text'])
        source,counts=create_source_from_document(db,user,document,'general',bundle['academic_year'],entry.get('academic_year',bundle['academic_year']),settings)
        source.kind=entry['kind'];source.url=entry['url'];source.verification=entry.get('verification','pending');source.source_location=entry.get('location','Fuente pública contrastada');source.checked_at=utcnow();source.warnings=entry.get('warnings',[])
        results.append({'source_id':source.id,**counts})
    if bundle.get('school_calendar'):
        profile=db.scalar(select(LearnerProfile).where(LearnerProfile.user_id==user.id));profile.preferences={**profile.preferences,'school_calendar':bundle['school_calendar']}
    if bundle.get('public_school_info'):
        center=db.get(Center,user.center_id);center.settings={**center.settings,'public_info':bundle['public_school_info']}
    db.commit()
    if not user.active:
        setup=db.scalar(select(AccountSetup).where(AccountSetup.user_id==user.id))
        if not setup or setup.expires_at<utcnow():
            if setup:db.delete(setup);db.flush()
            token=secrets.token_urlsafe(40)
            db.add(AccountSetup(user_id=user.id,token_hash=digest(token),expires_at=utcnow()+timedelta(hours=24)))
            db.commit()
            link=settings.data_dir/'private-account-setup.txt'
            link.write_text('http://127.0.0.1:8000/#setup='+token+'\n');link.chmod(0o600)
    return {'user_id':user.id,'active':user.active,'imports':results,'setup_file':str(settings.data_dir/'private-account-setup.txt') if not user.active else None}
