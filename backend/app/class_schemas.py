from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, AwareDatetime, Field, model_validator

from .schemas import Input

Identifier = Annotated[str, Field(min_length=1, max_length=36)]
ShortText = Annotated[str, Field(min_length=1, max_length=160)]
Answer = Annotated[str, Field(max_length=2000)]
Color = Literal['mint', 'sky', 'amber', 'orchid', 'coral']


def academic_date(value: datetime):
    if not 2000 <= value.year <= 2100:
        raise ValueError('Indica una fecha entre 2000 y 2100')
    return value


ClassDate = Annotated[AwareDatetime, AfterValidator(academic_date)]


class ClassInput(Input):
    name: str = Field(min_length=1, max_length=140)
    description: str = Field(default='', max_length=2500)
    color: Color = 'mint'


class ClassCreate(ClassInput):
    group_id: Identifier
    subject_id: Identifier


class ArchiveInput(Input):
    archived: bool


class JoinInput(Input):
    code: str = Field(min_length=16, max_length=64, pattern=r'^[A-Za-z0-9_-]+$')


class MemberInput(Input):
    username: str = Field(min_length=3, max_length=100, pattern=r'^[a-z0-9._@-]+$')


class PostInput(Input):
    title: ShortText
    content: str = Field(min_length=1, max_length=8000)
    pinned: bool = False
    comments_open: bool = False


class CommentInput(Input):
    content: str = Field(min_length=1, max_length=2000)


class TopicInput(Input):
    name: str = Field(min_length=1, max_length=100)


class TeamInput(TopicInput):
    students: list[Identifier] = Field(min_length=2, max_length=20)


class QuestionInput(Input):
    prompt: str = Field(min_length=1, max_length=450)
    options: list[ShortText] = Field(default_factory=list, max_length=8)

    @model_validator(mode='after')
    def validate_options(self):
        if len(self.options) == 1 or len(set(self.options)) != len(self.options):
            raise ValueError('Escribe dos o más opciones distintas o deja la pregunta abierta')
        return self


class RubricInput(Input):
    title: ShortText
    description: str = Field(default='', max_length=1000)
    points: int = Field(ge=1, le=1000)


class ActivityInput(Input):
    title: ShortText
    instructions: str = Field(min_length=1, max_length=12000)
    kind: Literal['task', 'exercise', 'quiz', 'project', 'exam'] = 'task'
    delivery: Literal['individual', 'team'] = 'individual'
    topic_id: Identifier | None = None
    due_at: ClassDate | None = None
    exam_at: ClassDate | None = None
    exam_minutes: int = Field(default=60, ge=15, le=360)
    max_points: int | None = Field(default=None, ge=1, le=1000)
    questions: list[QuestionInput] = Field(default_factory=list, max_length=20)
    rubric: list[RubricInput] = Field(default_factory=list, max_length=15)

    @model_validator(mode='after')
    def validate_activity(self):
        if self.questions and self.kind not in ('quiz', 'exam'):
            raise ValueError('Las preguntas corresponden a cuestionarios o exámenes')
        if self.exam_at and self.kind != 'exam':
            raise ValueError('La hora de examen requiere una actividad de tipo examen')
        if self.rubric and sum(item.points for item in self.rubric) != self.max_points:
            raise ValueError('La suma de la rúbrica debe coincidir con la puntuación máxima')
        return self


class ActivityState(Input):
    status: Literal['published', 'closed']


class SubmissionInput(Input):
    version: int = Field(ge=0)
    content: str = Field(default='', max_length=12000)
    answers: list[Answer] = Field(default_factory=list, max_length=20)
    submit: bool = False


class ReturnInput(Input):
    version: int = Field(ge=1)
    feedback: str = Field(min_length=1, max_length=6000)
    points: int | None = Field(default=None, ge=0, le=1000)
    criteria_scores: list[Annotated[int, Field(ge=0, le=1000)]] = Field(default_factory=list, max_length=15)


class ClassEventInput(Input):
    title: ShortText
    description: str = Field(default='', max_length=2500)
    kind: Literal['event', 'session', 'exam'] = 'event'
    starts_at: ClassDate
    ends_at: ClassDate

    @model_validator(mode='after')
    def validate_range(self):
        if self.ends_at <= self.starts_at:
            raise ValueError('El evento debe terminar después de empezar')
        return self


class AssistInput(Input):
    prompt: str = Field(min_length=3, max_length=1600)
    mode: Literal[
        'explain', 'review', 'practice', 'pending', 'plan', 'activity', 'quiz',
        'material', 'rubric', 'summary', 'conflicts', 'unit', 'level', 'feedback',
    ] = 'explain'
    use_memory: bool = False
