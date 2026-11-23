from typing import Literal
from pydantic import Field,AwareDatetime,model_validator
from .schemas import Input,ScheduleChange

class SetupInspect(Input):
    token:str=Field(min_length=32,max_length=100)
class SetupFinish(SetupInspect):
    password:str=Field(min_length=12,max_length=128)
class Availability(Input):
    weekday:int=Field(ge=0,le=6)
    starts:str=Field(pattern=r'^\d{2}:\d{2}$')
    ends:str=Field(pattern=r'^\d{2}:\d{2}$')
    @model_validator(mode='after')
    def times(self):
        from datetime import time
        time.fromisoformat(self.starts);time.fromisoformat(self.ends)
        if self.ends<=self.starts:raise ValueError('El final debe ser posterior al inicio')
        return self
class LearnerUpdate(Input):
    preferences:dict[str,str|bool|int]=Field(default_factory=dict,max_length=20)
    availability:list[Availability]=Field(default_factory=list,max_length=30)
    subject_ids:list[str]=Field(max_length=30)
class ProgressInput(Input):
    state:Literal['not_started','in_progress','review','mastered']
    confidence:int=Field(default=0,ge=0,le=5)
    notes:str=Field(default='',max_length=4000)
class AcademicQuery(Input):
    query:str=Field(default='',max_length=600)
    subject_id:str|None=None
    day:str|None=None
class CalculatorInput(Input):
    policy_id:str
    operation:Literal['term','final','recovery','extraordinary','target']='term'
    values:dict=Field(default_factory=dict,max_length=50)
    simulation:bool=True
    acknowledge_historical:bool=False
    target:float=Field(default=5,ge=0,le=10)
    unknown_component:str|None=Field(default=None,max_length=80)
class StudyInput(Input):
    subject_id:str
    topic:str=Field(min_length=2,max_length=200)
    mode:Literal['guided','quiz','mock']='guided'
class StudyAnswer(Input):
    exercise_id:str
    answer:str=Field(min_length=1,max_length=3000)
class PlanInput(Input):
    start_day:str|None=Field(default=None,max_length=10)
    days:int=Field(default=7,ge=1,le=21)
    subject_id:str|None=None
    session_minutes:int=Field(default=30,ge=15,le=90)
    max_sessions:int=Field(default=6,ge=1,le=20)
class PlanConfirm(Input):
    plan_id:str
class PersonalTaskInput(Input):
    title:str=Field(min_length=3,max_length=180)
    description:str=Field(default='',max_length=6000)
    due_at:AwareDatetime
    subject_id:str|None=None
class PersonalTaskUpdate(Input):
    completed:bool
class PrivateSlotUpdate(Input):
    starts:str=Field(pattern=r'^\d{2}:\d{2}$')
    ends:str=Field(pattern=r'^\d{2}:\d{2}$')
    classroom:str=Field(default='',max_length=60)
    teacher:str=Field(default='',max_length=120)
    @model_validator(mode='after')
    def times(self):
        from datetime import time
        time.fromisoformat(self.starts);time.fromisoformat(self.ends)
        if self.ends<=self.starts:raise ValueError('Intervalo inválido')
        return self
class AcademicImport(Input):
    document_id:str
    kind:Literal['physics','technology','english','schedule','general']='general'
    subject_id:str|None=None
    academic_year:str|None=Field(default=None,max_length=20)
    applicable_year:str=Field(default='2026-2027',max_length=20)
class MemoryUpdate(Input):
    content:str=Field(min_length=1,max_length=5000)
    category:Literal['personal','preference','reminder']='personal'
    event_at:AwareDatetime|None=None
    expected_updated_at:AwareDatetime
class ResearchInput(Input):
    query:str=Field(default='',max_length=250)
    url:str|None=Field(default=None,max_length=2000)
    consent:bool=False
class SyncInput(Input):
    simulation:bool=False
class NotificationPreferences(Input):
    enabled:bool=True
    advance_hours:int=Field(default=24,ge=1,le=168)
    frequency:Literal['daily','immediate']='daily'
    priority:Literal['all','important']='all'


class ManualKnowledge(Input):
    subject_id:str
    title:str=Field(min_length=3,max_length=180)
    text:str=Field(min_length=20,max_length=20000)
    academic_year:str|None=Field(default=None,max_length=20)
    applicable_year:str=Field(default='2026-2027',max_length=20)
    weights:dict[str,float]=Field(default_factory=dict,max_length=15)
    final_weights:list[float]=Field(default_factory=list,max_length=3)
    @model_validator(mode='after')
    def complete_weights(self):
        import math
        for key,value in self.weights.items():
            if not key or len(key)>60 or not math.isfinite(value) or value<=0 or value>100:raise ValueError('Ponderación no válida')
        if self.weights and abs(sum(self.weights.values())-100)>.000001:raise ValueError('Los porcentajes deben sumar 100')
        if self.final_weights and (len(self.final_weights)!=3 or any(not math.isfinite(v) or v<=0 for v in self.final_weights) or abs(sum(self.final_weights)-100)>.000001):raise ValueError('Las tres evaluaciones deben sumar 100 %')
        return self
