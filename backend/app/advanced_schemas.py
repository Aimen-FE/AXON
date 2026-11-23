from typing import Literal
from pydantic import Field, AwareDatetime, model_validator
from .schemas import Input

class MathInput(Input):
    operation: Literal['evaluate','simplify','solve','differentiate','integrate','statistics','verify'] = 'evaluate'
    expression: str = Field(default='', max_length=500)
    variable: Literal['x','y','z','t'] = 'x'
    comparison: str = Field(default='', max_length=500)
    values: list[float] = Field(default_factory=list, max_length=500)
    @model_validator(mode='after')
    def required(self):
        import math
        if any(not math.isfinite(v) or abs(v)>1e12 for v in self.values): raise ValueError('Datos fuera de rango')
        if self.operation=='statistics' and not self.values: raise ValueError('Introduce una lista de datos')
        if self.operation!='statistics' and not self.expression.strip(): raise ValueError('Introduce una expresión')
        if self.operation=='verify' and not self.comparison.strip(): raise ValueError('Introduce la expresión que quieres comprobar')
        return self

class SemanticQuery(Input):
    query: str = Field(min_length=2, max_length=300)
    day: str | None = Field(default=None, max_length=10)
    limit: int = Field(default=12, ge=1, le=30)

class AnnotationInput(Input):
    state: Literal['confirmed','provisional']

class DossierInput(Input):
    query: str = Field(default='', max_length=250)
    urls: list[str] = Field(default_factory=list, max_length=3)
    consent: bool = False
    @model_validator(mode='after')
    def bounded_urls(self):
        if any(len(url)>2000 for url in self.urls): raise ValueError('URL demasiado larga')
        if not self.query and not self.urls: raise ValueError('Indica un tema o páginas públicas')
        return self

class AutomationInput(Input):
    title: str = Field(min_length=3, max_length=160)
    kind: Literal['upcoming_exams','schedule_conflicts','stale_documents','academic_report','backup']
    interval_hours: int = Field(default=24, ge=1, le=168)
    next_run_at: AwareDatetime

class AutomationUpdate(Input):
    enabled: bool

class MaterialInput(Input):
    subject_id: str
    title: str = Field(min_length=3, max_length=180)
    kind: Literal['summary','cards','quiz','outline','exam_guide','rubric'] = 'summary'
    query: str = Field(min_length=2, max_length=300)

class MaterialUpdate(Input):
    content: str = Field(min_length=20, max_length=20000)
    version: int = Field(ge=1)
    reviewed: bool = False

class MaterialShare(Input):
    material_id: str
    group_id: str
    version: int = Field(ge=1)
