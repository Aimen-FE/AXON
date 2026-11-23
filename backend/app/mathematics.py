import json
import subprocess
import sys
import threading
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from .auth import current_user
from .advanced_schemas import MathInput

router=APIRouter(prefix='/math',tags=['Matemáticas deterministas'])
_capacity=threading.BoundedSemaphore(2)

def calculate_math(args):
    if not _capacity.acquire(blocking=False):raise HTTPException(429,'El motor matemático está ocupado. Inténtalo de nuevo en unos segundos')
    try:return _calculate(args)
    finally:_capacity.release()

def _calculate(args):
    worker=Path(__file__).with_name('math_worker.py')
    try:
        result=subprocess.run([sys.executable,'-I','-B',str(worker)],input=args.model_dump_json(),
            text=True,capture_output=True,timeout=7,cwd='/tmp',env={'LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'})
        if result.returncode or len(result.stdout)>15000:
            raise HTTPException(422,'La operación superó los límites de recursos o no pudo completarse')
        output=json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        raise HTTPException(422,'La operación superó el tiempo máximo de cálculo')
    except (ValueError,OSError):
        raise HTTPException(503,'El motor matemático no está disponible')
    if not output.get('ok'): raise HTTPException(422,output.get('message','Expresión no admitida'))
    return {'engine':'sympy-restricted','operation':args.operation,'result':output['result'],
        'official_grade':False,'limits':{'cpu_seconds':3,'wall_seconds':7,'memory_mb':768,'arbitrary_code':False,'external_io':False}}

@router.post('')
def calculate(body:MathInput,user=Depends(current_user)):
    return calculate_math(body)
