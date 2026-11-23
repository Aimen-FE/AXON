import {ClassEvaluationPanel,ClassSolutionPanel} from './class-settings-ui';
import {useState, type FormEvent} from 'react';
import {ArrowLeft, CalendarDays, Check, ClipboardList, History, LockKeyhole, Paperclip, Plus, Send} from 'lucide-react';
import {api, fmt, localValue, madridIso, post} from './api';
import {Badge, Empty, ErrorBox, Field, Loading, Modal, useAxon, useLoad, useTask} from './core';
import {FileForm, FileLink} from './class-file-ui';
import {
  ACTIVITY_LABELS, ACTIVITY_STATUS, FILE_TYPES, WORK_STATUS, type ActivityKind, type ActivityRow, type ClassActivity,
  type ClassGrade, type ClassQuestion, type ClassRoom, type ClassSubmission, type ClassTopic, type RubricCriterion, type WorkRevision,
} from './class-types';

export function ClassActivities({path, room, activityId}: {path: string; room: ClassRoom; activityId?: string}) {
  const {data, error, loading} = useLoad<ActivityRow[]>(path + '/activities');
  const {navigate, refresh, notify} = useAxon();
  const [creating, setCreating] = useState(false);
  const [filter, setFilter] = useState('all');
  const route = 'classes/' + room.id + '/activities';
  const rows = data?.filter(item => filter === 'all' || item.status === filter) ?? [];
  if (activityId) return <ActivityWorkspace path={path} room={room} activityId={activityId} key={activityId}/>;
  return <>
    <div className="class-section-heading">
      <h2>Actividades de clase</h2>
      {room.can_manage && !room.archived && <button className="primary" onClick={() => setCreating(true)}><Plus size={17}/> Nueva actividad</button>}
    </div>
    <ErrorBox error={error}/>{loading && !data && <Loading/>}
    {!!data?.length && <div className="class-filter"><Field label="Estado">
      <select value={filter} onChange={event => setFilter(event.target.value)}><option value="all">Todas las actividades</option>
        {Object.entries(ACTIVITY_STATUS).filter(([value]) => value !== 'draft' || room.can_manage).map(([value, label]) =>
          <option key={value} value={value}>{label}</option>)}
      </select>
    </Field></div>}
    {data && !rows.length && <Empty title="No hay actividades en esta vista">Las actividades publicadas traen sus instrucciones y fechas de entrega.</Empty>}
    <div className="class-activity-list">{rows.map(item => <button className="class-activity-row" key={item.id}
      onClick={() => navigate(route + '/' + item.id)}>
      <span className="class-activity-icon">{item.locked ? <LockKeyhole size={20}/> : <ClipboardList size={20}/>}</span>
      <span className="class-activity-name"><small>{ACTIVITY_LABELS[item.kind]}{item.delivery === 'team' && ' · En equipo'}</small>
        <strong>{item.title}</strong>{item.due_at && <span>Entrega {fmt(item.due_at, {dateStyle: 'medium', timeStyle: 'short'})}</span>}
      </span>
      <Badge tone={item.status === 'draft' ? 'amber' : 'gray'}>{item.submission ? WORK_STATUS[item.submission.status] : ACTIVITY_STATUS[item.status]}</Badge>
    </button>)}</div>
    {creating && <ActivityForm path={path} close={() => setCreating(false)} onSaved={result => {
      setCreating(false); refresh(); notify('Borrador guardado'); navigate(route + '/' + result.id);
    }}/>}
  </>;
}

export function ActivityForm({path, activity, initialText, close, onSaved}: {
  path: string; activity?: ClassActivity; initialText?: string; close: () => void; onSaved: (result: ClassActivity) => void;
}) {
  const {data: topics, error: topicError} = useLoad<ClassTopic[]>(path + '/topics');
  const [kind, setKind] = useState<ActivityKind>(activity?.kind ?? 'task');
  const [questions, setQuestions] = useState<ClassQuestion[]>(activity?.questions ?? []);
  const [rubric, setRubric] = useState<RubricCriterion[]>(activity?.rubric ?? []);
  const t = useTask();
  const changeQuestion = (index: number, edit: Partial<ClassQuestion>) =>
    setQuestions(items => items.map((question, i) => i === index ? {...question, ...edit} : question));
  const changeCriterion = (index: number, edit: Partial<RubricCriterion>) =>
    setRubric(items => items.map((criterion, i) => i === index ? {...criterion, ...edit} : criterion));
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    t.run(async () => {
      const due = String(form.get('due_at') || '');
      const exam = String(form.get('exam_at') || '');
      const points = String(form.get('max_points') || '');
      const body = {
        title: form.get('title'), instructions: form.get('instructions'), topic_id: form.get('topic_id') || null,
        delivery: form.get('delivery'), kind, due_at: due ? madridIso(due) : null,
        exam_at: kind === 'exam' && exam ? madridIso(exam) : null, exam_minutes: Number(form.get('exam_minutes') || 60),
        max_points: rubric.length ? rubric.reduce((total, criterion) => total + criterion.points, 0) : points ? Number(points) : null,
        questions: kind === 'quiz' || kind === 'exam' ? questions.map(item => ({
          prompt: item.prompt.trim(), options: item.options.map(option => option.trim()).filter(Boolean),
        })) : [],
        rubric,
      };
      const endpoint = path + '/activities';
      onSaved(activity ? await api<ClassActivity>(endpoint + '/' + activity.id, {method: 'PUT', body: JSON.stringify(body)})
        : await post<ClassActivity>(endpoint, body));
    });
  };
  return <Modal title={activity ? 'Editar borrador' : 'Nueva actividad'} onClose={close} wide>
    <form onSubmit={submit}>
      <Field label="Título"><input name="title" required maxLength={160} defaultValue={activity?.title}/></Field>
      <div className="form-grid">
        <Field label="Tipo"><select value={kind} onChange={event => setKind(event.target.value as ActivityKind)}>
          {Object.entries(ACTIVITY_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></Field>
        <Field label="Entrega"><select name="delivery" defaultValue={activity?.delivery ?? 'individual'}>
          <option value="individual">Individual</option><option value="team">En equipo</option>
        </select></Field>
      </div>
      <Field label="Instrucciones"><textarea name="instructions" rows={5} required maxLength={12000}
        defaultValue={activity?.instructions ?? initialText?.slice(0, 12000)}/></Field>
      <div className="form-grid">
        <Field label="Tema"><select name="topic_id" defaultValue={activity?.topic_id ?? ''}>
          <option value="">Sin tema</option>{topics?.map(topic => <option key={topic.id} value={topic.id}>{topic.name}</option>)}
        </select></Field>
        <Field label="Fecha límite (Madrid)"><input type="datetime-local" name="due_at"
          defaultValue={activity?.due_at ? localValue(activity.due_at) : ''}/></Field>
      </div>
      {kind === 'exam' && <div className="form-grid">
        <Field label="Inicio del examen (Madrid)"><input type="datetime-local" name="exam_at"
          defaultValue={activity?.exam_at ? localValue(activity.exam_at) : ''}/></Field>
        <Field label="Duración en minutos"><input type="number" min={15} max={360} name="exam_minutes" defaultValue={activity?.exam_minutes ?? 60}/></Field>
      </div>}
      {(kind === 'quiz' || kind === 'exam') && <section className="class-form-section">
        <div className="class-section-heading"><h3>Preguntas</h3>
          <button type="button" className="secondary" disabled={questions.length >= 20} onClick={() => setQuestions(items => [...items, {prompt: '', options: []}])}>Añadir pregunta</button>
        </div>
        {questions.map((question, index) => <fieldset className="class-editor-group" key={index}>
          <legend>Pregunta {index + 1}</legend>
          <Field label="Enunciado"><input value={question.prompt} required maxLength={450} onChange={event => changeQuestion(index, {prompt: event.target.value})}/></Field>
          <Field label="Opciones, una por línea (opcional)"><textarea rows={3} value={question.options.join('\n')}
            maxLength={1300} onChange={event => changeQuestion(index, {options: event.target.value.split('\n')})}/></Field>
          <button type="button" className="text-button" onClick={() => setQuestions(items => items.filter((_, i) => i !== index))}>Quitar pregunta</button>
        </fieldset>)}
      </section>}
      <section className="class-form-section">
        <div className="class-section-heading"><h3>Evaluación</h3>
          <button type="button" className="secondary" disabled={rubric.length >= 15}
            onClick={() => setRubric(items => [...items, {title: '', description: '', points: 1}])}>Añadir criterio</button></div>
        {!rubric.length && <Field label="Puntuación máxima (opcional)">
          <input type="number" name="max_points" min={1} max={1000} defaultValue={activity?.max_points ?? ''}/>
        </Field>}
        {rubric.map((criterion, index) => <fieldset className="class-editor-group" key={index}>
          <legend>Criterio {index + 1}</legend>
          <div className="form-grid"><Field label="Criterio"><input value={criterion.title} required maxLength={160}
            onChange={event => changeCriterion(index, {title: event.target.value})}/></Field>
            <Field label="Puntos máximos"><input type="number" min={1} max={1000} value={criterion.points || ''}
              required onChange={event => changeCriterion(index, {points: Number(event.target.value)})}/></Field></div>
          <Field label="Descripción"><textarea value={criterion.description} rows={2} maxLength={1000}
            onChange={event => changeCriterion(index, {description: event.target.value})}/></Field>
          <button type="button" className="text-button" onClick={() => setRubric(items => items.filter((_, i) => i !== index))}>Quitar criterio</button>
        </fieldset>)}
        {!!rubric.length && <p className="fine-print">Puntuación máxima de la rúbrica {rubric.reduce((sum, item) => sum + item.points, 0)}</p>}
      </section>
      <ErrorBox error={t.error || topicError}/><button className="primary" disabled={t.busy}>Guardar borrador</button>
    </form>
  </Modal>;
}

function ActivityWorkspace({path, room, activityId}: {path: string; room: ClassRoom; activityId: string}) {
  const workPath = path + '/activities/' + activityId;
  const {data, error, loading} = useLoad<ClassActivity>(workPath);
  const {navigate, refresh, notify} = useAxon();
  const [modal, setModal] = useState('');
  const t = useTask();
  const writable = room.can_manage && !room.archived;
  return <>
    <button className="text-button class-back" onClick={() => navigate('classes/' + room.id + '/activities')}>
      <ArrowLeft size={17}/> Todas las actividades
    </button>
    <ErrorBox error={error || t.error}/>{loading && !data && <Loading/>}
    {data && <>
      <article className="class-panel class-instructions">
        <div className="class-section-heading">
          <div><p className="class-inline-label">{ACTIVITY_LABELS[data.kind]}{data.delivery === 'team' && ' · En equipo'}</p><h2>{data.title}</h2></div>
          <Badge tone={data.status === 'draft' ? 'amber' : 'green'}>{ACTIVITY_STATUS[data.status]}</Badge>
        </div>
        {(data.due_at || data.exam_at) && <div className="class-activity-dates">
          <CalendarDays size={17}/>
          <span>{data.exam_at && <>Inicio {fmt(data.exam_at, {dateStyle: 'medium', timeStyle: 'short'})} · </>}
            {data.due_at && <>Entrega {fmt(data.due_at, {dateStyle: 'medium', timeStyle: 'short'})}</>}
          </span>
        </div>}
        {data.locked ? <p className="muted">Las instrucciones y la entrega se abrirán al comenzar el examen.</p>
          : <p className="pre-wrap">{data.instructions}</p>}
        {data.files.map(file => <div className="class-file-line" key={file.id}>
          <FileLink file={file}/>
          {writable && <button className="text-button" disabled={t.busy} onClick={() => {
            if (confirm('¿Retirar el adjunto?')) t.run(async () => {
              await api(path + '/files/' + file.id, {method: 'DELETE'}); refresh(); notify('Adjunto retirado');
            });
          }}>Retirar</button>}
        </div>)}
        {writable && <div className="button-row class-activity-actions">
          <button className="secondary" onClick={() => setModal('file')}><Paperclip size={16}/> Adjuntar archivo</button>
          {data.status === 'draft' && <button className="secondary" onClick={() => setModal('edit')}>Editar borrador</button>}
          <button className={data.status === 'draft' ? 'primary' : 'secondary'} onClick={() => setModal('state')}>
            {data.status === 'draft' ? 'Publicar actividad' : data.status === 'closed' ? 'Reabrir entregas' : 'Cerrar entregas'}
          </button>
        </div>}
      </article>
      {room.can_manage && data.questions.length > 0 && <section className="class-panel class-instructions">
        <h3>Preguntas del {data.kind === 'exam' ? 'examen' : 'cuestionario'}</h3>
        <ol>{data.questions.map((item, index) => <li key={index}>{item.prompt}{!!item.options.length && <span className="muted"> · {item.options.join(' / ')}</span>}</li>)}</ol>
      </section>}
      {!!data.rubric.length && <section className="class-panel class-instructions">
        <h3>Rúbrica de evaluación</h3>
        <div className="class-criteria">{data.rubric.map((criterion, index) => <div key={index}>
          <div><strong>{criterion.title}</strong>{criterion.description && <p>{criterion.description}</p>}</div>
          <Badge tone="gray">{criterion.points} pts</Badge>
        </div>)}</div>
      </section>}
      {room.can_manage&&<ClassSolutionPanel path={workPath} writable={writable}/>}
      {room.can_manage && data.status !== 'draft' && <ReviewQueue path={workPath} activity={data} writable={writable}/>}
      {!room.can_manage && !data.locked && <StudentWork path={workPath} activity={data} room={room}/>}
      {modal === 'file' && <FileForm path={path + '/files'} activityId={data.id} close={() => setModal('')}/>}
      {modal === 'edit' && <ActivityForm path={path} activity={data} close={() => setModal('')} onSaved={() => {
        setModal(''); refresh(); notify('Borrador actualizado');
      }}/>}
      {modal === 'state' && <Modal title={data.status === 'draft' ? 'Publicar actividad' : data.status === 'closed' ? 'Reabrir entregas' : 'Cerrar entregas'} onClose={() => setModal('')}>
        <p>{data.status === 'draft' ? 'La clase recibirá un aviso y la fecha se añadirá al calendario.' : data.status === 'closed'
          ? 'El alumnado podrá entregar hasta la fecha límite publicada.' : 'Las entregas y calificaciones existentes seguirán disponibles.'}</p>
        <ErrorBox error={t.error}/><button className="primary" disabled={t.busy} onClick={() => t.run(async () => {
          const status = data.status === 'published' ? 'closed' : 'published';
          await api(workPath + '/state', {method: 'PUT', body: JSON.stringify({status})});
          setModal(''); refresh(); notify(status === 'published' ? 'Actividad publicada' : 'Entregas cerradas');
        })}>{data.status === 'draft' ? 'Publicar para la clase' : data.status === 'closed' ? 'Reabrir' : 'Cerrar entregas'}</button>
      </Modal>}
    </>}
  </>;
}

function StudentWork({path, activity, room}: {path: string; activity: ClassActivity; room: ClassRoom}) {
  const {data, error, loading, setData} = useLoad<ClassSubmission | null>(path + '/submission');
  const {user} = useAxon();
  const {data: people} = useLoad<import('./class-types').ClassPeople>('/classes/' + room.id + '/people');
  if (loading && !data) return <Loading/>;
  if (error && !data) return <ErrorBox error={error}/>;
  const team = people?.teams.find(item => item.students.includes(user.id));
  const writeable = !room.archived && activity.status === 'published' && !!activity.due_at &&
    Date.parse(activity.due_at) >= Date.now() && data?.status !== 'submitted' && (activity.delivery !== 'team' || !!team);
  return <SubmissionEditor path={path} activity={activity} data={data} setData={setData} writable={writeable}
    teamName={team?.name} reloadError={error}/>;
}

function SubmissionEditor({path, activity, data, setData, writable, teamName, reloadError}: {
  path: string; activity: ClassActivity; data: ClassSubmission | null; setData: (data: ClassSubmission) => void;
  writable: boolean; teamName?: string; reloadError: string;
}) {
  const [{text, answers}, setDraft] = useState(() => ({text: data?.content || '', answers: data?.answers || []}));
  const [history, setHistory] = useState(false);
  const [confirmSend, setConfirmSend] = useState(false);
  const {notify, refresh} = useAxon();
  const t = useTask();
  const [version, setVersion] = useState(data?.version ?? 0);
  const acceptSaved = (result: ClassSubmission) => {
    setData(result);
    setVersion(result.version);
  };
  const upload = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const body = new FormData(form);
    body.set('version', String(version));
    t.run(async () => {
      const result = await api<ClassSubmission>(path + '/submission/files', {method: 'POST', body});
      acceptSaved(result); form.reset(); notify('Adjunto guardado en el borrador');
    });
  };
  const save = (submit: boolean) => t.run(async () => {
    const actualAnswers = activity.questions.map((_, index) => answers[index] || '');
    const result = await api<ClassSubmission>(path + '/submission', {
      method: 'PUT', body: JSON.stringify({version, content: text, answers: actualAnswers, submit}),
    });
    acceptSaved(result); setConfirmSend(false); refresh(); notify(submit ? 'Entrega enviada al profesorado' : 'Borrador guardado');
  });
  return <section className="class-panel class-submission">
    <div className="class-section-heading"><div>
      <h3>{teamName ? 'Entrega de ' + teamName : 'Mi entrega'}</h3>
      {teamName && <p className="muted">El equipo comparte el borrador y la corrección.</p>}
    </div>{data && <Badge tone={data.status === 'submitted' ? 'green' : 'amber'}>{WORK_STATUS[data.status]}</Badge>}</div>
    <ErrorBox error={t.error || reloadError}/>
    {data && data.version !== version && <button className="secondary" onClick={() => {
      setDraft({text: data.content, answers: data.answers}); setVersion(data.version);
    }}>Cargar la última versión</button>}
    {activity.delivery === 'team' && !teamName && <p>El profesorado debe asignarte a un equipo para que puedas entregar.</p>}
    {writable ? <>
      {activity.questions.map((question, index) => <Field key={index} label={question.prompt}>
        {question.options.length ? <select value={answers[index] || ''} onChange={event => {
          const value = event.target.value;
          setDraft(previous => {const next = [...previous.answers]; next[index] = value; return {...previous, answers: next}});
        }}><option value="">Selecciona una respuesta</option>{question.options.map(option => <option key={option}>{option}</option>)}</select>
          : <textarea rows={2} maxLength={2000} value={answers[index] || ''} onChange={event => {
            const value = event.target.value;
            setDraft(previous => {const next = [...previous.answers]; next[index] = value; return {...previous, answers: next}});
          }}/>}
      </Field>)}
      <Field label={activity.questions.length ? 'Notas para el profesor (opcional)' : 'Respuesta'}><textarea rows={5} maxLength={12000}
        value={text} onChange={event => setDraft({text: event.target.value, answers})}/></Field>
    </> : data && <SubmissionText activity={activity} content={data.content} answers={data.answers}/>}
    {data?.files.map(file => <div className="class-file-line" key={file.id}>
      <FileLink file={file} href={'/api' + path + '/submissions/' + data.id + '/files/' + file.id}/>
      {writable && <button className="text-button" disabled={t.busy} onClick={() => t.run(async () => {
        const result = await api<ClassSubmission>(path + '/submission/files/' + file.id + '?version=' + version, {method: 'DELETE'});
        acceptSaved(result); notify('Adjunto retirado del borrador');
      })}>Retirar</button>}
    </div>)}
    {writable && <>
      {(data?.files.length ?? 0) < 5 && <form className="class-attach-form" onSubmit={upload}>
        <Field label="Añadir un archivo"><input type="file" name="file" accept={FILE_TYPES} required/></Field>
        <button className="secondary" disabled={t.busy}><Paperclip size={16}/> Adjuntar</button>
      </form>}
      <div className="button-row">
        <button className="secondary" disabled={t.busy} onClick={() => save(false)}>Guardar borrador</button>
        <button className="primary" disabled={t.busy} onClick={() => setConfirmSend(true)}><Send size={16}/> Entregar</button>
      </div>
    </>}
    {!writable && !data && activity.delivery !== 'team' && <p className="muted">El plazo de entrega está cerrado.</p>}
    {data?.grade && <GradeCard grade={data.grade} activity={activity}/>}
    {data && <button className="text-button" onClick={() => setHistory(true)}><History size={16}/> Historial de la entrega</button>}
    {history && data && <RevisionHistory path={path + '/submissions/' + data.id} activity={activity} close={() => setHistory(false)}/>}
    {confirmSend && <Modal title="Confirmar entrega" onClose={() => setConfirmSend(false)}>
      <p>El profesorado recibirá esta versión de tu respuesta y los archivos que has adjuntado.</p>
      <ErrorBox error={t.error}/>
      <button className="primary" disabled={t.busy} onClick={() => save(true)}><Send size={16}/> Enviar entrega</button>
    </Modal>}
  </section>;
}

function SubmissionText({activity, content, answers}: {activity: ClassActivity; content: string; answers: string[]}) {
  return <>
    {!!answers.length && <dl className="class-answers">{activity.questions.map((question, index) => <div key={index}>
      <dt>{question.prompt}</dt><dd className="pre-wrap">{answers[index] || 'Sin respuesta'}</dd>
    </div>)}</dl>}
    {content && <p className="pre-wrap">{content}</p>}
  </>;
}

function GradeCard({grade, activity}: {grade: ClassGrade; activity: ClassActivity}) {
  return <section className="class-grade-card">
    <div className="class-section-heading"><h4><Check size={17}/> Corrección del profesorado</h4>
      {grade.points !== null && <Badge>{grade.points} / {activity.max_points}</Badge>}
    </div>
    <p className="pre-wrap">{grade.feedback}</p>
    {!!grade.criteria_scores.length && <ul>{grade.criteria_scores.map((points, i) => <li key={i}>
      {activity.rubric[i]?.title} <strong>{points} / {activity.rubric[i]?.points}</strong>
    </li>)}</ul>}
  </section>;
}

function ReviewQueue({path, activity, writable}: {path: string; activity: ClassActivity; writable: boolean}) {
  const {data, error, loading} = useLoad<ClassSubmission[]>(path + '/submissions');
  const [reviewing, setReviewing] = useState<ClassSubmission | null>(null);
  return <section className="class-panel class-submission">
    <div className="class-section-heading"><h3>Entregas del alumnado</h3>
      {data && <span className="muted">{data.filter(item => item.status === 'submitted').length} por corregir</span>}
    </div>
    <ErrorBox error={error}/>{loading && !data && <Loading/>}
    {data?.length === 0 && <p className="muted">Todavía no hay entregas enviadas.</p>}
    {data?.map(submission => <div className="class-review-row" key={submission.id}>
      <div><strong>{submission.author_name}</strong>
        {submission.submitted_at && <small>{fmt(submission.submitted_at, {dateStyle: 'medium', timeStyle: 'short'})}</small>}</div>
      <Badge tone={submission.status === 'returned' ? 'green' : 'amber'}>{WORK_STATUS[submission.status]}</Badge>
      <button className="secondary" onClick={() => setReviewing(submission)}>{submission.status === 'returned' ? 'Ver corrección' : 'Revisar'}</button>
    </div>)}
    {reviewing && <ReviewForm path={path + '/submissions/' + reviewing.id} activity={activity} item={reviewing}
      writable={writable} close={() => setReviewing(null)}/>}
  </section>;
}

function ReviewForm({path, activity, item, writable, close}: {
  path: string; activity: ClassActivity; item: ClassSubmission; writable: boolean; close: () => void;
}) {
  const {refresh, notify} = useAxon();
  const [history, setHistory] = useState(false);
  const t = useTask();
  if (history) return <RevisionHistory path={path} activity={activity} close={() => setHistory(false)}/>;
  return <Modal title={'Entrega de ' + item.author_name} onClose={close} wide>
    <SubmissionText activity={activity} content={item.content} answers={item.answers}/>
    {item.files.map(file => <FileLink key={file.id} file={file} href={'/api' + path + '/files/' + file.id}/>)}
    <button className="text-button" onClick={() => setHistory(true)}><History size={17}/> Ver historial</button>
    {writable ? <form onSubmit={event => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      t.run(async () => {
        await post(path + '/return', {
          version: item.version, feedback: form.get('feedback'),
          points: form.get('points') ? Number(form.get('points')) : null,
          criteria_scores: form.getAll('score').map(Number),
        });
        refresh(); close(); notify('Corrección devuelta al alumnado');
      });
    }}>
      <Field label="Comentario de corrección"><textarea name="feedback" rows={4} maxLength={6000} required defaultValue={item.grade?.feedback}/></Field>
      {activity.rubric.map((criterion, index) => <Field key={index} label={criterion.title + ' (hasta ' + criterion.points + ' puntos)'}>
        <input type="number" name="score" min={0} max={criterion.points} required defaultValue={item.grade?.criteria_scores[index]}/>
      </Field>)}
      {activity.max_points && !activity.rubric.length && <Field label={'Puntuación de 0 a ' + activity.max_points}>
        <input type="number" name="points" min={0} max={activity.max_points} defaultValue={item.grade?.points ?? ''}/>
      </Field>}
      <ErrorBox error={t.error}/><button className="primary" disabled={t.busy}>Devolver corrección</button>
    </form> : item.grade && <GradeCard grade={item.grade} activity={activity}/>}
  </Modal>;
}

const changeLabels: Record<string, string> = {
  draft: 'Borrador guardado', submitted: 'Entrega enviada', returned: 'Corrección devuelta',
  file_added: 'Adjunto añadido', file_removed: 'Adjunto retirado',
};

function RevisionHistory({path, activity, close}: {path: string; activity: ClassActivity; close: () => void}) {
  const {data, error, loading} = useLoad<WorkRevision[]>(path + '/history');
  return <Modal title="Historial de la entrega" onClose={close} wide>
    <ErrorBox error={error}/>{loading && !data && <Loading/>}
    <div className="class-stream">{data?.map(item => <details key={item.id} className="class-history-row">
      <summary><strong>{changeLabels[item.change] || item.change}</strong>
        <small>Versión {item.version} · {fmt(item.created_at, {dateStyle: 'medium', timeStyle: 'short'})}</small>
      </summary>
      <SubmissionText activity={activity} content={item.snapshot.content} answers={item.snapshot.answers}/>
      {item.snapshot.files.map(file => <FileLink key={file.id} file={file} href={'/api' + path + '/files/' + file.id}/>)}
      {item.snapshot.grade && <GradeCard grade={item.snapshot.grade} activity={activity}/>}
    </details>)}</div>
  </Modal>;
}

type GradeRow = ClassGrade & {activity_id: string; title: string; max_points: number | null; author_name: string};
export function ClassGrades({path, room}: {path: string; room: ClassRoom}) {
  const {data, error, loading} = useLoad<GradeRow[]>(path + '/grades');
  const {navigate} = useAxon();
  return <>
    <div className="class-section-heading"><h2>{room.can_manage ? 'Calificaciones de la clase' : 'Mis calificaciones'}</h2></div>
    <ClassEvaluationPanel path={path} writable={room.can_manage&&!room.archived}/>
    <ErrorBox error={error}/>{loading && !data && <Loading/>}
    {data?.length === 0 && <Empty title="Aún no hay calificaciones">Las correcciones se muestran después de que el profesorado las devuelva.</Empty>}
    <div className="class-stream">{data?.map(grade => <article className="class-panel class-grade-row" key={grade.id}>
      <div className="class-section-heading"><div><h3>{grade.title}</h3>{room.can_manage && <span className="muted">{grade.author_name}</span>}</div>
        <Badge tone="green">{grade.points === null ? 'Corregida' : grade.points + ' / ' + grade.max_points}</Badge>
      </div>
      <p className="pre-wrap">{grade.feedback}</p>
      <button className="text-button" onClick={() => navigate('classes/' + room.id + '/activities/' + grade.activity_id)}>Abrir actividad</button>
    </article>)}</div>
  </>;
}
