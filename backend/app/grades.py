"""Motor decimal determinista. Simula; nunca publica calificaciones oficiales."""
from decimal import Decimal,InvalidOperation,ROUND_FLOOR,ROUND_HALF_UP
from fastapi import HTTPException
from sqlalchemy import select
from .models import AssessmentPolicy,KnowledgeSource
from .serializers import record


LABELS={'exams':'Pruebas escritas','activities':'Actividades','practical':'Prácticas y trabajos','participation':'Participación','projects':'Proyectos y tareas','e1':'Primera evaluación','e2':'Segunda evaluación','e3':'Tercera evaluación','previous':'Nota anterior','exam':'Prueba de recuperación','use_of_english':'Use of English'}
def label(key):return LABELS.get(key,key.replace('_',' ').capitalize())

def number(value,name='nota'):
    if isinstance(value,bool):raise HTTPException(422,f'{name}: debe ser una nota numérica')
    try:n=Decimal(str(value))
    except (InvalidOperation,ValueError,TypeError):raise HTTPException(422,f'{name}: debe ser una nota numérica')
    if not n.is_finite() or n<0 or n>10:raise HTTPException(422,f'{name}: debe estar entre 0 y 10')
    return n

def encoded(n):return format(n.quantize(Decimal('0.000001')).normalize(),'f')

def calculate(db,user,args):
    policy=db.scalar(select(AssessmentPolicy).where(AssessmentPolicy.id==args.policy_id,AssessmentPolicy.owner_id==user.id))
    if not policy:raise HTTPException(404,'Reglas de evaluación no disponibles')
    source=db.scalar(select(KnowledgeSource).where(KnowledgeSource.id==policy.source_id,KnowledgeSource.owner_id==user.id))
    if source.verification=='historical' and not args.acknowledge_historical:
        raise HTTPException(409,'La fuente es histórica. Confirma expresamente una simulación con sus reglas; no se aplicará como vigente')
    if not args.simulation and source.verification not in ('teacher_confirmed','official_verified'):
        raise HTTPException(409,'La fuente está pendiente de validación; solo se permite una simulación personal identificada')
    warnings=list(source.warnings)
    if policy.scheme=='manual':warnings.append('Media aritmética con porcentajes aportados por el titular; no se aplican mínimos, recuperaciones o redondeos no especificados')
    if source.verification not in ('teacher_confirmed','official_verified'):warnings.append('Estimación personal según una fuente no validada institucionalmente')
    values=args.values
    if 'term_index' in values and (type(values['term_index']) is not int or values['term_index'] not in (1,2,3)):raise HTTPException(422,'Evaluación debe ser 1, 2 o 3')
    for key in ('improvement','use_of_english_passed','minimum_exam_conditions_confirmed','use_of_english_all_terms_passed'):
        if key in values and type(values[key]) is not bool:raise HTTPException(422,f'{key}: se requiere una confirmación explícita')
    steps=[];missing=[];conditions=policy.conditions;raw=None;grade=None;passed=None
    operation=args.operation
    if operation in ('term','target'):
        if operation=='target' and args.unknown_component in ('e1','e2','e3') and len(policy.final_weights)==3:
            total_weight=sum(Decimal(str(v)) for v in policy.final_weights)
            weights={f'e{i+1}':Decimal(str(v))*100/total_weight for i,v in enumerate(policy.final_weights)}
        else:weights={k:Decimal(str(v)) for k,v in policy.weights.items()}
        if not weights or abs(sum(weights.values())-100)>Decimal('0.0000001'):
            return {'status':'missing_information','missing':['Ponderaciones completas que sumen 100 %'],'warnings':warnings,'source':record(source),'official':False}
        unknown=args.unknown_component if operation=='target' else None
        if unknown and unknown not in weights:raise HTTPException(422,'El componente desconocido no figura en estas reglas')
        total=Decimal(0)
        calculated={}
        for key,weight in weights.items():
            if key==unknown:continue
            if key not in values:missing.append(key);continue
            value=values[key]
            if policy.scheme=='english' and isinstance(value,dict):
                if set(value)!={'tests','work'}:missing.append(key+': tests y work');continue
                n=number(value['tests'],key)*Decimal('.9')+number(value['work'],key)*Decimal('.1')
                steps.append(f'{label(key)}: pruebas × 0,90 + trabajos × 0,10 = {encoded(n)}')
            else:n=number(value,key)
            total+=n*weight/100;calculated[key]=n
            steps.append(f'{label(key)}: {encoded(n)} × {weight}% = {encoded(n*weight/100)}')
        if not missing:
            if operation=='target':
                if not unknown:raise HTTPException(422,'Indica el componente cuya nota quieres calcular')
                needed=(number(args.target,'objetivo')-total)/(weights[unknown]/100)
                raw=needed
                steps.append(f'Necesaria en {label(unknown)}: ({args.target} − {encoded(total)}) / ({weights[unknown]}/100) = {encoded(needed)}')
                return {'status':'calculated','required':encoded(needed),'reachable':needed<=10,'already_reached':needed<=0,'steps':steps,'warnings':warnings+['Las condiciones especiales también deben cumplirse'],'source':record(source),'official':False}
            raw=total;grade=raw;passed=raw>=5
            if policy.scheme=='english':
                if any(n<Decimal(conditions.get('minimum_skill','1')) for n in calculated.values()):
                    grade=min(grade,Decimal('4'));passed=False;steps.append('Destreza inferior a 1: la calificación queda limitada a 4')
                if 'use_of_english_passed' not in values:missing.append('Confirmación de al menos un examen aprobado de Use of English en esta evaluación')
                elif values['use_of_english_passed'] is not True:passed=False;warnings.append('No se cumple el requisito de Use of English aprobado')
            if policy.scheme=='english' and not any(n<Decimal(conditions.get('minimum_skill','1')) for n in calculated.values()):
                integer=grade.to_integral_value(rounding=ROUND_FLOOR);grade=integer+1 if grade-integer>=Decimal('.75') else integer
                steps.append('Boletín: aproximación al alza desde 0,75 según la fuente histórica')
            if policy.scheme=='physics' and conditions.get('term_rounding')=='truncate' and values.get('term_index',1) in (1,2):
                grade=grade.to_integral_value(rounding=ROUND_FLOOR);steps.append('Boletín de 1.ª/2.ª evaluación: truncar, conservando decimales para cálculos posteriores')
            if policy.scheme=='technology':warnings.append('El documento indica aproximar a entero; no especifica el umbral exacto. Se conserva el valor decimal')
    elif operation=='final':
        weights=[Decimal(str(x)) for x in policy.final_weights]
        if len(weights)!=3 or sum(weights)<=0:missing.append('Fórmula de las tres evaluaciones')
        terms=[]
        for key in ('e1','e2','e3'):
            if key not in values:missing.append(key)
            else:terms.append(number(values[key],key))
        if not missing:
            raw=sum(n*w for n,w in zip(terms,weights))/sum(weights);grade=raw;passed=raw>=5
            steps.append('('+' + '.join(f'{encoded(n)} × {w}' for n,w in zip(terms,weights))+f') / {sum(weights)} = {encoded(raw)}')
            failed=[n for n in terms if n<5]
            if policy.scheme in ('physics','technology') and raw>=5 and (len(failed)>=2 or any(n<Decimal('3.5') for n in failed)):
                grade=Decimal(4);passed=False;steps.append('Dos evaluaciones suspensas o una suspensa por debajo de 3,5: calificación final 4')
            if policy.scheme=='philosophy':
                if failed:missing.append('Condición exacta para aprobar por media con evaluaciones suspensas')
                if values.get('minimum_exam_conditions_confirmed') is not True:missing.append('Verificar al menos dos pruebas por evaluación, ninguna inferior a 4 y actividades con mínimo 4')
            if policy.scheme=='english':
                if values.get('use_of_english_all_terms_passed') is not True:missing.append('Verificar Use of English aprobado en cada evaluación y mínimos por destreza')
            if policy.scheme=='physics' and conditions.get('final_rounding')=='half_up_except_fail':
                grade=Decimal(4) if Decimal('4.5')<=grade<5 else grade.quantize(Decimal(1),rounding=ROUND_HALF_UP)
                steps.append('Redondeo final desde 0,5; entre 4,5 y 4,99 se mantiene 4')
            elif policy.scheme=='philosophy':
                if raw<5:missing.append('Aplicación exacta del redondeo cuando la media sin redondear es suspensa')
                integer=grade.to_integral_value(rounding=ROUND_FLOOR)
                grade=integer+1 if grade-integer>=Decimal('.7') else integer
                warnings.append('Redondeo desde siete décimas según lo aportado; condicionado a las reglas completas de aprobación')
            elif policy.scheme=='english':
                if Decimal('4.75')<=raw<5:missing.append('Confirmar aplicación del redondeo final: la fuente exige extraordinaria si la media ponderada es inferior a 5')
                integer=grade.to_integral_value(rounding=ROUND_FLOOR);grade=integer+1 if grade-integer>=Decimal('.75') else integer
            elif policy.scheme=='technology':warnings.append('Se conserva la nota decimal: umbral exacto de aproximación no especificado')
    elif operation=='recovery':
        if not conditions.get('recovery_mean'):missing.append('Regla concreta de recuperación en esta fuente')
        if 'previous' not in values:missing.append('previous')
        if 'exam' not in values:missing.append('exam')
        if not missing:
            old,exam=number(values['previous']),number(values['exam']);raw=(old+exam)/2;grade=raw
            improvement=values.get('improvement') is True
            if improvement and old<5:raise HTTPException(422,'Mejora de nota exige una evaluación previamente aprobada')
            if exam>=5 or improvement:grade=max(Decimal('5'),grade)
            passed=grade>=5;steps.append(f'({old} + {exam}) / 2 = {encoded(raw)}; mínimo 5 si aprueba recuperación o se presenta a mejora')
    elif operation=='extraordinary':
        if policy.scheme=='english':
            extra=conditions.get('extraordinary_weights',{})
            if not extra or sum(Decimal(v) for v in extra.values())!=100:missing.append('Ponderaciones completas de la convocatoria extraordinaria')
            elif any(k not in values for k in extra):missing.extend(k for k in extra if k not in values)
            else:
                raw=sum(number(values[k],k)*Decimal(w)/100 for k,w in extra.items());grade=raw;passed=raw>=5
                steps.append('Suma de destrezas con ponderaciones extraordinarias, distintas de las ordinarias')
        elif conditions.get('extraordinary_weight')=='100' and 'exam' in values:
            raw=number(values['exam']);grade=raw;passed=raw>=5;steps.append('Prueba extraordinaria × 100 %')
            if policy.scheme=='physics':grade=Decimal(4) if Decimal('4.5')<=raw<5 else raw.quantize(Decimal(1),rounding=ROUND_HALF_UP)
        else:missing.append('Nota de la prueba y regla completa de convocatoria extraordinaria')
    if grade is not None and grade<5:passed=False
    if missing:passed=None
    return {'status':'missing_information' if missing else 'calculated','raw':encoded(raw) if raw is not None else None,'grade':encoded(grade) if grade is not None else None,
        'passed':passed,'missing':missing,'steps':steps,'warnings':warnings,'source':record(source),'official':False}
