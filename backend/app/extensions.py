"""Static, reviewable extension manifests. No uploaded plugin code is executed."""
import importlib.util
from dataclasses import dataclass
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from .auth import current_user, get_db
from .models import CenterModule
from .policy import require_role, audit
from .schemas import Input

router = APIRouter(tags=['Módulos'])

@dataclass(frozen=True)
class Module:
    title: str
    functions: tuple[str, ...]
    dependencies: tuple[str, ...] = ()
    configuration: tuple[str, ...] = ()
    tests: str = 'test_agent03.py'

MODULES = {
    'agent': Module('Agente de varios pasos', (), (), (), 'test_agent03.py'),
    'semantic': Module('Memoria semántica local', ('search_semantic_memory',), ('fastembed',), ('data/models/semantic-model.json',), 'test_semantic03.py'),
    'math': Module('Matemáticas verificables', ('calculate_math',), ('sympy',), (), 'test_math03.py'),
    'research': Module('Investigación pública', ('search_public','research_sources'), (), ('AXON_SEARCH_URL (opcional)',), 'test_research03.py'),
    'classroom': Module('Classroom de solo lectura', (), ('cryptography',), ('AXON_GOOGLE_CLIENT_ID','AXON_GOOGLE_CLIENT_SECRET'), 'test_learning_security.py'),
    'tutor': Module('Estudio y planificación', ('get_study_context','create_study_plan','save_study_plan'), (), (), 'test_learning.py'),
    'scheduler': Module('Automatizaciones personales', (), (), (), 'test_operations03.py'),
    'materials': Module('Materiales revisables', ('share_material',), (), (), 'test_operations03.py'),
}
TOOL_MODULE = {name: key for key, module in MODULES.items() for name in module.functions}
PATH_MODULE = {'/api/study':'tutor','/api/research':'research','/api/integrations/classroom':'classroom',
               '/api/semantic':'semantic','/api/math':'math','/api/automations':'scheduler','/api/materials':'materials'}
MANIFEST_PATHS={**PATH_MODULE,'/api/agent':'agent'}

def enabled(db, user, key):
    row = db.scalar(select(CenterModule).where(CenterModule.center_id == user.center_id, CenterModule.key == key))
    return row is None or row.enabled

def require_module(db, user, key):
    if not enabled(db, user, key):
        raise HTTPException(409, f'El módulo «{MODULES[key].title}» está desactivado para este centro')

def enforce_path(request, user, db):
    path = request.url.path
    # Revocation is always possible even while the integration is disabled.
    if path.endswith('/revoke'): return
    for prefix, key in PATH_MODULE.items():
        if path == prefix or path.startswith(prefix + '/'):
            require_module(db, user, key)
            return

class ModuleUpdate(Input):
    enabled: bool

@router.get('/modules')
def manifests(request: Request, user=Depends(current_user), db=Depends(get_db)):
    from .tools import CATALOG
    from .semantic import semantic_status
    result = []
    spec=request.app.openapi()
    for key, module in MODULES.items():
        missing = [dep for dep in module.dependencies if importlib.util.find_spec(dep) is None]
        configured = not missing
        if key == 'semantic': configured = configured and semantic_status(request.app.state.settings)['available']
        if key == 'classroom':
            from .classroom import config
            configured = all(config())
        operations=[]
        for prefix,owner in MANIFEST_PATHS.items():
            if owner!=key:continue
            for path,methods in spec['paths'].items():
                if path!=prefix and not path.startswith(prefix+'/'):continue
                for method,operation in methods.items():
                    if not isinstance(operation,dict) or 'operationId' not in operation:continue
                    schema=operation.get('requestBody',{}).get('content',{}).get('application/json',{}).get('schema',{'type':'object','properties':{}})
                    if '$ref' in schema:schema=spec.get('components',{}).get('schemas',{}).get(schema['$ref'].split('/')[-1],schema)
                    operations.append({'name':operation['operationId'],'method':method.upper(),'path':path,'arguments':schema,
                        'parameters':operation.get('parameters',[]),'roles':['student','teacher','admin'],'authorization':'Titular y ámbito comprobados en backend; operaciones institucionales restringidas a personal autorizado'})
        result.append({'key':key,'title':module.title,'enabled':enabled(db,user,key),
            'status':'ready' if configured else 'configuration_required','dependencies':module.dependencies,
            'configuration':module.configuration,'tests':module.tests,'api_operations':operations,
            'functions':[{'name':n,'arguments':CATALOG[n].schema.model_json_schema(),
                'roles':CATALOG[n].roles,'confirmation_level':CATALOG[n].level} for n in module.functions if n in CATALOG]})
    return result

@router.patch('/admin/modules/{key}')
def toggle(key: str, body: ModuleUpdate, user=Depends(current_user), db=Depends(get_db)):
    require_role(user,'admin')
    if key not in MODULES: raise HTTPException(404,'Módulo no disponible')
    # Dependants may only be enabled when their prerequisites are active.
    row = db.scalar(select(CenterModule).where(CenterModule.center_id==user.center_id,CenterModule.key==key))
    if row is None:
        row = CenterModule(center_id=user.center_id,key=key); db.add(row)
    row.enabled = body.enabled
    db.flush(); audit(db,user,'module_configured',row,{'module':key,'enabled':body.enabled}); db.commit()
    return {'key':key,'enabled':row.enabled}
