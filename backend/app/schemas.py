from datetime import time
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, model_validator, field_validator


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Login(Input):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=128)


class ConversationCreate(Input):
    title: str = Field(default='Nueva conversación', min_length=1, max_length=140)


class ChatInput(Input):
    content: str = Field(min_length=1, max_length=6000)
    client_id: str = Field(min_length=8, max_length=80)


class MemoryInput(Input):
    content: str = Field(min_length=1, max_length=5000)
    category: Literal['personal', 'preference', 'reminder'] = 'personal'
    event_at: AwareDatetime | None = None


class EventArgs(Input):
    title: str = Field(min_length=3, max_length=180)
    description: str = Field(default='', max_length=8000)
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    group_id: str | None = None
    subject_id: str | None = None
    classroom_id: str | None = None
    visibility: Literal['personal', 'group', 'center'] = 'group'
    kind: Literal['exam', 'event', 'reminder', 'meeting'] = 'event'
    syllabus: str = Field(default='', max_length=6000)

    @model_validator(mode='after')
    def dates(self):
        if self.ends_at <= self.starts_at:
            raise ValueError('El final debe ser posterior al inicio')
        if (self.ends_at - self.starts_at).total_seconds() > 14 * 86400:
            raise ValueError('Duración máxima: 14 días')
        if self.visibility == 'group' and not self.group_id:
            raise ValueError('Selecciona un grupo')
        if self.visibility != 'group' and self.group_id:
            raise ValueError('Los eventos personales o del centro no llevan grupo')
        if self.kind == 'exam' and (self.visibility != 'group' or not self.subject_id):
            raise ValueError('Un examen necesita grupo y asignatura')
        return self


class EventUpdate(Input):
    event_id: str
    version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=3, max_length=180)
    description: str | None = Field(default=None, max_length=8000)
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None


class EventCancel(Input):
    event_id: str
    version: int = Field(ge=1)


class AssignmentArgs(Input):
    title: str = Field(min_length=3, max_length=180)
    description: str = Field(default='', max_length=10000)
    group_id: str
    subject_id: str
    due_at: AwareDatetime
    material_ids: list[str] = Field(default_factory=list, max_length=10)


class SubmissionInput(Input):
    content: str = Field(default='', max_length=12000)
    status: Literal['submitted', 'completed'] = 'submitted'


class ScheduleItem(Input):
    group_id: str
    subject_id: str
    teacher_id: str
    classroom_id: str | None = None
    weekday: int = Field(ge=0, le=4)
    starts: str = Field(pattern=r'^\d{2}:\d{2}$')
    ends: str = Field(pattern=r'^\d{2}:\d{2}$')

    @model_validator(mode='after')
    def times(self):
        time.fromisoformat(self.starts)
        time.fromisoformat(self.ends)
        if self.ends <= self.starts:
            raise ValueError('Hora final inválida')
        return self


class ScheduleArgs(Input):
    entries: list[ScheduleItem] = Field(min_length=1, max_length=100)


class NotificationArgs(Input):
    group_id: str | None = None
    title: str = Field(min_length=3, max_length=180)
    content: str = Field(min_length=1, max_length=6000)


class ValidateDocumentArgs(Input):
    document_id: str
    status: Literal['validated', 'official'] = 'validated'


class ToolCall(Input):
    tool: str = Field(min_length=1, max_length=80)
    arguments: dict = Field(default_factory=dict)


class QueryArgs(Input):
    query: str = Field(default='', max_length=300)
    day: str | None = Field(default=None, pattern=r'^\d{4}-\d{2}-\d{2}$')


class EmptyArgs(Input):
    pass


class BathroomArgs(Input):
    student_id: str
    group_id: str


class ReturnArgs(Input):
    pass_id: str


class PassCorrection(Input):
    left_at: AwareDatetime
    returned_at: AwareDatetime | None = None
    reason: str = Field(min_length=10, max_length=300)

    @model_validator(mode='after')
    def dates(self):
        if self.returned_at and self.returned_at < self.left_at:
            raise ValueError('Regreso anterior a la salida')
        return self


class PreferencesInput(Input):
    theme: Literal['light', 'dark', 'system'] = 'system'
    notifications: dict[str, bool] = Field(default_factory=dict, max_length=12)
    automatic_personal_actions: bool = True
    conversation_retention_days: int | None = Field(default=None,ge=30,le=3650)

    @field_validator('notifications')
    @classmethod
    def categories(cls, value):
        if set(value) - {'exam','assignment','event','announcement','reminder','action'}:
            raise ValueError('Categoría de aviso desconocida')
        return value


class PasswordInput(Input):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class DeleteDataInput(Input):
    password: str = Field(max_length=128)
    confirmation: Literal['ELIMINAR MIS DATOS']


class UserCreate(Input):
    username: str = Field(min_length=3, max_length=100, pattern=r'^[a-z0-9._@-]+$')
    display_name: str = Field(min_length=3, max_length=100)
    role: Literal['student','teacher','admin']
    password: str = Field(min_length=12, max_length=128)
    group_ids: list[str] = Field(default_factory=list, max_length=20)


class UserUpdate(Input):
    active: bool | None = None
    role: Literal['student','teacher','admin'] | None = None

    @model_validator(mode='after')
    def require_change(self):
        if self.active is None and self.role is None:
            raise ValueError('Indica el estado o el rol de la cuenta')
        return self


class GroupCreate(Input):
    course_id: str
    name: str = Field(min_length=2, max_length=100)


class TeachingInput(Input):
    teacher_id: str
    group_id: str
    subject_id: str


class CenterInput(Input):
    name: str = Field(min_length=5, max_length=160)
    town: str = Field(min_length=2, max_length=100)
    bathroom_retention_days: int = Field(default=14, ge=1, le=90)
    automation_enabled: bool = True


class ReviewDecision(Input):
    decision: Literal['accepted','rejected']


class ExamArgs(EventArgs):
    kind: Literal['exam'] = 'exam'
    visibility: Literal['group'] = 'group'


class StructureInput(Input):
    kind: Literal['year','course','subject','classroom']
    name: str = Field(min_length=2,max_length=100)
    year_id: str | None = None
    stage: str = Field(default='ESO',min_length=2,max_length=50)
    color: str = Field(default='#176c5d',pattern=r'^#[0-9a-fA-F]{6}$')


class EnrollmentInput(Input):
    student_id: str
    group_id: str


class AssignmentUpdate(Input):
    assignment_id: str
    expected_updated_at: AwareDatetime
    title: str | None = Field(default=None,min_length=3,max_length=180)
    description: str | None = Field(default=None,max_length=10000)
    due_at: AwareDatetime | None = None


class ScheduleChange(Input):
    schedule_id: str
    expected_updated_at: AwareDatetime
    weekday: int = Field(ge=0,le=4)
    starts: str = Field(pattern=r'^\d{2}:\d{2}$')
    ends: str = Field(pattern=r'^\d{2}:\d{2}$')
    classroom_id: str | None = None

    @model_validator(mode='after')
    def times(self):
        time.fromisoformat(self.starts);time.fromisoformat(self.ends)
        if self.ends<=self.starts:raise ValueError('Hora final inválida')
        return self


class ScheduleDelete(Input):
    schedule_id: str
    expected_updated_at: AwareDatetime
