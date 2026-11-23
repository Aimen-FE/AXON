import {ClassAdmissionPanel} from './class-settings-ui';
import {useState, type FormEvent} from 'react';
import {
  ArrowLeft, ArrowRight, Bell, BookOpen, CalendarDays, ClipboardList, KeyRound, Layers3,
  Megaphone, Pin, Plus, Settings2, Sparkles, UsersRound,
} from 'lucide-react';
import {api, fmt, madridIso, post} from './api';
import {Badge, Empty, ErrorBox, Field, Loading, Modal, useAxon, useLoad, useTask} from './core';
import {ActivityForm, ClassActivities, ClassGrades} from './class-work-ui';
import {FileForm, FileLink} from './class-file-ui';
import {
  type ClassColor, type ClassComment, type ClassDirectory, type ClassFile, type ClassPeople,
  type ClassPost, type ClassRoom, type ClassTopic,
} from './class-types';
import type {Event} from './types';
import './classes.css';

const tabs = [
  {id: 'board', title: 'Tablón', icon: Megaphone},
  {id: 'activities', title: 'Actividades', icon: ClipboardList},
  {id: 'materials', title: 'Materiales', icon: Layers3},
  {id: 'people', title: 'Personas', icon: UsersRound},
  {id: 'grades', title: 'Calificaciones', icon: BookOpen},
  {id: 'calendar', title: 'Calendario', icon: CalendarDays},
];
const colors: {id: ClassColor; name: string}[] = [
  {id: 'mint', name: 'Verde'}, {id: 'sky', name: 'Azul'}, {id: 'amber', name: 'Ámbar'},
  {id: 'orchid', name: 'Violeta'}, {id: 'coral', name: 'Coral'},
];

export default function ClassesView({route}: {route: string}) {
  const [newClass, setNewClass] = useState<ClassRoom | null>(null);
  const [, room, tab, activity] = route.split('/');
  if (room && /^[a-zA-Z0-9-]{1,36}$/.test(room)) {
    return <ClassWorkspace key={room} id={room} tab={tabs.some(item => item.id === tab) ? tab : 'board'}
      activity={activity && /^[a-zA-Z0-9-]{1,36}$/.test(activity) ? activity : undefined}
      initialCode={newClass?.id === room ? newClass.join_code : undefined} clearCode={() => setNewClass(null)}/>;
  }
  return <Directory onCreated={setNewClass}/>;
}

function Directory({onCreated}: {onCreated: (room: ClassRoom) => void}) {
  const {user, navigate, refresh, notify} = useAxon();
  const {data, error, loading} = useLoad<ClassDirectory>('/classes');
  const [modal, setModal] = useState('');
  const [showArchived, setShowArchived] = useState(false);
  const [stage,setStage]=useState(''),[course,setCourse]=useState(''),[group,setGroup]=useState(''),[subject,setSubject]=useState('');
  const t = useTask();
  const rooms = data?.classes.filter(room => (showArchived ? room.archived : !room.archived)&&(!stage||room.stage===stage)&&(!course||room.course===course)&&(!group||room.group===group)&&(!subject||room.subject===subject)) ?? [];
  const join = async (room: ClassRoom & {pending?:boolean}) => {
    if(room.pending){setModal('');notify('Solicitud enviada al profesorado');return;}
    setModal('');
    refresh();
    navigate('classes/' + room.id);
    notify('Ya formas parte de ' + room.name);
  };
  return <section className="classes-screen">
    <header className="class-index-head">
      <div><h1>Clases</h1><p>Tu espacio para aprender, trabajar y compartir en AXON.</p></div>
      <button className="primary" onClick={() => setModal(user.role === 'student' ? 'join' : 'create')}>
        {user.role === 'student' ? <><KeyRound size={18}/> Unirme con código</> : <><Plus size={18}/> Nueva clase</>}
      </button>
    </header>
    <ErrorBox error={error}/>
    {loading && !data && <Loading/>}
    {!!data?.invitations.length && <section className="class-invitations" aria-label="Invitaciones">
      <h2><Bell size={18}/> Invitaciones para ti</h2>
      {data.invitations.map(invitation => <div className="class-invitation" key={invitation.id}>
        <div><strong>{invitation.name}</strong><small>{invitation.subject} · Hasta {fmt(invitation.expires_at)}</small></div>
        <button className="secondary" disabled={t.busy} onClick={() => t.run(async () =>
          join(await post<ClassRoom>('/classes/' + invitation.id + '/accept'))
        )}>Aceptar invitación</button>
      </div>)}
    </section>}
    {!!data?.classes.some(room => room.archived) && <div className="class-list-toggle">
      <button className={!showArchived ? 'selected' : ''} aria-pressed={!showArchived} onClick={() => setShowArchived(false)}>En curso</button>
      <button className={showArchived ? 'selected' : ''} aria-pressed={showArchived} onClick={() => setShowArchived(true)}>Archivadas</button>
    </div>}
    {data&&data.classes.length>0&&<div className="class-directory-filters">
      {([['Etapa',stage,setStage,'stage'],['Curso',course,setCourse,'course'],['Grupo',group,setGroup,'group'],['Asignatura',subject,setSubject,'subject']] as const).map(([label,value,change,key])=><Field key={key} label={label}><select value={value} onChange={event=>change(event.target.value)}><option value="">Todas las opciones</option>{[...new Set(data.classes.map(room=>room[key]))].sort().map(option=><option key={option} value={option}>{option}</option>)}</select></Field>)}
    </div>}
    {rooms.length > 0 && <div className="class-grid">
      {rooms.map(room => <button className="class-cover" data-class-color={room.color} key={room.id}
        onClick={() => navigate('classes/' + room.id)}>
        <span className="class-cover-mark"><BookOpen size={27}/></span>
        <span className="class-cover-subject">{room.subject}</span>
        <strong>{room.name}</strong>
        <span className="class-cover-description">{room.description || room.course}</span>
        <span className="class-cover-bottom">{room.group} <ArrowRight aria-hidden size={18}/></span>
      </button>)}
    </div>}
    {data && !rooms.length && <Empty title={showArchived ? 'No hay clases archivadas' : 'Aún no tienes clases'}>
      {showArchived ? 'Las clases que archives aparecerán aquí.' : user.role === 'student'
        ? 'Acepta una invitación o pide un código a tu profesor.' : 'Crea una clase y comparte su código de inscripción con el alumnado.'}
    </Empty>}
    {modal === 'create' && <ClassForm close={() => setModal('')} onSaved={room => {
      onCreated(room); setModal(''); refresh(); notify('Clase creada'); navigate('classes/' + room.id + '/people');
    }}/>}
    {modal === 'join' && <Modal title="Unirme a una clase" onClose={() => setModal('')}>
      <form onSubmit={event => {
        event.preventDefault();
        const code = String(new FormData(event.currentTarget).get('code'));
        t.run(async () => join(await post<ClassRoom>('/classes/join', {code})));
      }}>
        <Field label="Código de inscripción"><input name="code" required minLength={16} maxLength={64}
          autoCapitalize="off" spellCheck={false} autoComplete="off"/></Field>
        <ErrorBox error={t.error}/>
        <button className="primary" disabled={t.busy}>Unirme</button>
      </form>
    </Modal>}
  </section>;
}

function ClassForm({room, close, onSaved}: {room?: ClassRoom; close: () => void; onSaved: (room: ClassRoom) => void}) {
  const {academic, user, navigate} = useAxon();
  const availableGroups = academic.groups.filter(group => user.role === 'admin' ||
    academic.teaching.some(item => item.teacher_id === user.id && item.group_id === group.id));
  const [group, setGroup] = useState(room?.group_id ?? availableGroups[0]?.id ?? '');
  const [color, setColor] = useState<ClassColor>(room?.color ?? 'mint');
  const t = useTask();
  const subjects = academic.subjects.filter(subject => user.role === 'admin' ||
    academic.teaching.some(item => item.teacher_id === user.id && item.group_id === group && item.subject_id === subject.id));
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body = {name: form.get('name'), description: form.get('description'), color};
    t.run(async () => onSaved(room
      ? await api<ClassRoom>('/classes/' + room.id, {method: 'PATCH', body: JSON.stringify(body)})
      : await post<ClassRoom>('/classes', {...body, group_id: group, subject_id: form.get('subject')})));
  };
  return <Modal title={room ? 'Editar clase' : 'Nueva clase'} onClose={close}>
    {!room && (!availableGroups.length || !academic.subjects.length) ? <>
      <Empty title="Falta la estructura de la clase">Necesitas un grupo y una asignatura autorizados.</Empty>
      {user.role === 'admin' && <button className="primary" onClick={() => {close(); navigate('admin')}}>Abrir Administración</button>}
    </> : <form onSubmit={submit}>
      <Field label="Nombre de la clase"><input name="name" required maxLength={140} defaultValue={room?.name}/></Field>
      {!room && <div className="form-grid">
        <Field label="Curso y grupo"><select value={group} onChange={event => setGroup(event.target.value)} required>
          {availableGroups.map(item => <option key={item.id} value={item.id}>
            {item.name} · {academic.courses.find(course => course.id === item.course_id)?.name}
          </option>)}
        </select></Field>
        <Field label="Asignatura"><select name="subject" key={group} required>
          {subjects.map(subject => <option value={subject.id} key={subject.id}>{subject.name}</option>)}
        </select></Field>
      </div>}
      <Field label="Descripción"><textarea name="description" rows={3} maxLength={2500} defaultValue={room?.description}/></Field>
      <fieldset className="class-color-picker"><legend>Color de la clase</legend>
        {colors.map(choice => <label key={choice.id} data-class-color={choice.id}>
          <input type="radio" name="class-color" value={choice.id} checked={color === choice.id} onChange={() => setColor(choice.id)}/>
          <span className="class-swatch"/>{choice.name}
        </label>)}
      </fieldset>
      <ErrorBox error={t.error}/>
      <button className="primary" disabled={t.busy || (!room && !subjects.length)}>{room ? 'Guardar cambios' : 'Crear clase'}</button>
    </form>}
  </Modal>;
}

function ClassWorkspace({id, tab, activity, initialCode, clearCode}: {
  id: string; tab: string; activity?: string; initialCode?: string; clearCode: () => void;
}) {
  const route = 'classes/' + id;
  const path = '/classes/' + id;
  const {data, error, loading} = useLoad<ClassRoom>(path);
  const {navigate, refresh, notify} = useAxon();
  const [modal, setModal] = useState('');
  const [assistantDraft, setAssistantDraft] = useState('');
  const t = useTask();
  if (!data || error) return <section className="classes-screen">
    <button className="text-button" onClick={() => navigate('classes')}><ArrowLeft size={17}/> Todas las clases</button>
    <ErrorBox error={error}/>{loading && <Loading/>}
  </section>;

  return <section className="classes-screen class-workspace" data-class-color={data.color}>
    <button className="text-button class-back" onClick={() => navigate('classes')}><ArrowLeft size={17}/> Todas las clases</button>
    <header className="class-room-head">
      <div>
        <p className="class-room-subject">{data.subject} <span>{data.group}</span></p>
        <h1>{data.name}</h1>
        {data.description && <p className="class-room-description">{data.description}</p>}
        {data.archived && <Badge tone="gray">Archivada</Badge>}
      </div>
      <div className="button-row">
        <button className="primary" onClick={() => setModal('ai')}><Sparkles size={17}/> Preguntar a AXON</button>
        {data.can_manage && <button className="secondary" onClick={() => setModal('settings')}><Settings2 size={17}/> Gestionar clase</button>}
      </div>
    </header>
    <nav className="class-tabs" aria-label="Secciones de la clase">
      {tabs.map(({id: key, title, icon: Icon}) => <button key={key} aria-current={key === tab ? 'page' : undefined}
        onClick={() => navigate(route + '/' + key)}><Icon size={17}/>{title}</button>)}
    </nav>
    <ErrorBox error={error}/>
    <div className="class-tab-content" key={tab}>
      {tab === 'board' && <Board path={path} room={data}/>}
      {tab === 'activities' && <ClassActivities path={path} room={data} activityId={activity}/>}
      {tab === 'materials' && <Materials path={path} room={data}/>}
      {tab === 'people' && <People path={path} room={data} initialCode={initialCode} clearCode={clearCode}/>}
      {tab === 'grades' && <ClassGrades path={path} room={data}/>}
      {tab === 'calendar' && <ClassCalendar path={path} room={data}/>}
    </div>
    {modal === 'settings' && <Modal title="Gestionar clase" onClose={() => setModal('')}>
      <div className="class-modal-actions">
        {!data.archived && <button className="secondary" onClick={() => setModal('edit')}>Editar datos de la clase</button>}
        <button className="secondary" disabled={t.busy} onClick={() => t.run(async () => {
          await api(path + '/archive', {method: 'PUT', body: JSON.stringify({archived: !data.archived})});
          refresh(); setModal(''); notify(data.archived ? 'Clase reabierta' : 'Clase archivada');
        })}>{data.archived ? 'Reabrir clase' : 'Archivar clase'}</button>
      </div>
      <p className="fine-print">Las clases archivadas siguen disponibles para consulta y se cierran a nuevas inscripciones y entregas.</p>
      <ErrorBox error={t.error}/>
    </Modal>}
    {modal === 'edit' && <ClassForm room={data} close={() => setModal('')} onSaved={() => {
      setModal(''); refresh(); notify('Cambios guardados');
    }}/>}
    {modal === 'ai' && <ClassAssistant path={path} room={data} close={() => setModal('')} onDraft={text => {
      setAssistantDraft(text); setModal('draft');
    }}/>}
    {modal === 'draft' && <ActivityForm path={path} initialText={assistantDraft} close={() => setModal('')} onSaved={result => {
      setModal(''); refresh(); notify('Borrador guardado'); navigate(route + '/activities/' + result.id);
    }}/>}
  </section>;
}

function Board({path, room}: {path: string; room: ClassRoom}) {
  const {data, error, loading} = useLoad<ClassPost[]>(path + '/posts');
  const [opened, setOpened] = useState('');
  const [editor, setEditor] = useState<ClassPost | 'new' | null>(null);
  const {refresh, notify} = useAxon();
  const t = useTask();
  const writable = room.can_manage && !room.archived;
  return <>
    <div className="class-section-heading"><h2>Tablón de la clase</h2>
      {writable && <button className="primary" onClick={() => setEditor('new')}><Plus size={17}/> Publicar aviso</button>}
    </div>
    <ErrorBox error={error}/>{loading && !data && <Loading/>}
    {data?.length === 0 && <Empty title="El tablón está vacío">Aquí aparecerán los avisos del profesorado.</Empty>}
    <div className="class-stream">{data?.map(postItem => <article className="class-panel class-post" key={postItem.id}>
      <div className="class-post-header">
        <div>{postItem.pinned && <span className="class-pinned"><Pin size={14}/> Aviso fijado</span>}
          <h3>{postItem.title}</h3><small>{postItem.author_name} · {fmt(postItem.created_at, {dateStyle: 'medium'})}</small>
        </div>
        {writable && <div className="button-row">
          <button className="text-button" onClick={() => setEditor(postItem)}>Editar</button>
          <button className="text-button" disabled={t.busy} onClick={() => {
            if (confirm('¿Ocultar este aviso?')) t.run(async () => {
              await api(path + '/posts/' + postItem.id, {method: 'DELETE'}); refresh(); notify('Aviso oculto');
            });
          }}>Ocultar</button>
        </div>}
      </div>
      <p className="pre-wrap">{postItem.content}</p>
      <button className="text-button" aria-expanded={opened === postItem.id}
        onClick={() => setOpened(opened === postItem.id ? '' : postItem.id)}>Comentarios</button>
      {opened === postItem.id && <Comments path={path + '/posts/' + postItem.id + '/comments'} postItem={postItem} room={room}/>}
    </article>)}</div>
    {editor && <PostForm path={path + '/posts'} item={editor === 'new' ? undefined : editor} close={() => setEditor(null)}/>}
  </>;
}

function PostForm({path, item, close}: {path: string; item?: ClassPost; close: () => void}) {
  const {refresh, notify} = useAxon();
  const t = useTask();
  return <Modal title={item ? 'Editar aviso' : 'Publicar aviso'} onClose={close}>
    <form onSubmit={event => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      const body = {title: form.get('title'), content: form.get('content'), pinned: form.has('pinned'), comments_open: form.has('comments')};
      t.run(async () => {
        if (item) await api(path + '/' + item.id, {method: 'PUT', body: JSON.stringify(body)});
        else await post(path, body);
        refresh(); close(); notify(item ? 'Aviso actualizado' : 'Aviso publicado');
      });
    }}>
      <Field label="Título"><input name="title" required maxLength={160} defaultValue={item?.title}/></Field>
      <Field label="Mensaje"><textarea name="content" rows={5} required maxLength={8000} defaultValue={item?.content}/></Field>
      <label className="class-check"><input type="checkbox" name="pinned" defaultChecked={item?.pinned}/> Fijar en el tablón</label>
      <label className="class-check"><input type="checkbox" name="comments" defaultChecked={item?.comments_open}/> Permitir comentarios</label>
      <ErrorBox error={t.error}/>
      <button className="primary" disabled={t.busy}>{item ? 'Guardar cambios' : 'Publicar'}</button>
    </form>
  </Modal>;
}

function Comments({path, postItem, room}: {path: string; postItem: ClassPost; room: ClassRoom}) {
  const {user, refresh, notify} = useAxon();
  const {data, error, loading} = useLoad<ClassComment[]>(path);
  const t = useTask();
  return <section className="class-comments">
    <ErrorBox error={error}/>{loading && !data && <Loading/>}
    {data?.map(comment => <div className="class-comment" key={comment.id}>
      <div><strong>{comment.author_name}</strong><p className="pre-wrap">{comment.content}</p></div>
      {!room.archived && (room.can_manage || comment.author_id === user.id) && <button className="text-button" disabled={t.busy}
        onClick={() => t.run(async () => {await api(path + '/' + comment.id, {method: 'DELETE'}); refresh(); notify('Comentario retirado')})}>Retirar</button>}
    </div>)}
    {data?.length === 0 && <p className="muted">Todavía no hay comentarios.</p>}
    {postItem.comments_open && !room.archived && <form onSubmit={event => {
      event.preventDefault();
      const form = event.currentTarget;
      const content = new FormData(form).get('content');
      t.run(async () => {await post(path, {content}); form.reset(); refresh(); notify('Comentario publicado')});
    }}>
      <Field label="Añadir comentario"><textarea name="content" maxLength={2000} required rows={2}/></Field>
      <button className="secondary" disabled={t.busy}>Comentar</button>
    </form>}
    <ErrorBox error={t.error}/>
  </section>;
}

function Materials({path, room}: {path: string; room: ClassRoom}) {
  const {data, error, loading} = useLoad<ClassFile[]>(path + '/files');
  const topics = useLoad<ClassTopic[]>(path + '/topics');
  const {refresh, notify} = useAxon();
  const [modal, setModal] = useState('');
  const t = useTask();
  const writable = room.can_manage && !room.archived;
  const folders = [...(topics.data || []), {id: null, name: 'Sin tema'}];
  return <>
    <div className="class-section-heading"><h2>Materiales de clase</h2>{writable && <div className="button-row">
      <button className="secondary" onClick={() => setModal('topic')}>Nuevo tema</button>
      <button className="primary" onClick={() => setModal('file')}><Plus size={17}/> Subir material</button>
    </div>}</div>
    <ErrorBox error={error || topics.error || t.error}/>{loading && !data && <Loading/>}
    {data?.length === 0 && !topics.data?.length && <Empty title="No hay materiales todavía">Los archivos de la clase aparecerán organizados por temas.</Empty>}
    <div className="class-stream">
      {folders.map(folder => {
        const files = data?.filter(file => file.topic_id === folder.id) ?? [];
        if (!folder.id && !files.length) return null;
        return <section className="class-panel class-folder" key={folder.id ?? 'general'}>
          <h3><Layers3 size={18}/> {folder.name}</h3>
          {files.length === 0 && <p className="muted">Este tema todavía está vacío.</p>}
          {files.map(file => <div key={file.id} className="class-file-line">
            <FileLink file={file}/>
            {writable && <button className="text-button" disabled={t.busy} onClick={() => {
              if (confirm('¿Retirar este material de la clase?')) t.run(async () => {
                await api(path + '/files/' + file.id, {method: 'DELETE'}); refresh(); notify('Material retirado');
              });
            }}>Retirar</button>}
          </div>)}
        </section>;
      })}
    </div>
    {modal === 'topic' && <Modal title="Nuevo tema" onClose={() => setModal('')}>
      <form onSubmit={event => {
        event.preventDefault();
        const name = new FormData(event.currentTarget).get('name');
        t.run(async () => {await post(path + '/topics', {name}); setModal(''); refresh(); notify('Tema creado')});
      }}>
        <Field label="Nombre del tema"><input name="name" required maxLength={100}/></Field>
        <ErrorBox error={t.error}/><button className="primary" disabled={t.busy}>Crear tema</button>
      </form>
    </Modal>}
    {modal === 'file' && <FileForm path={path + '/files'} topics={topics.data || []} close={() => setModal('')}/>}
  </>;
}

function People({path, room, initialCode, clearCode}: {path: string; room: ClassRoom; initialCode?: string; clearCode: () => void}) {
  const {data, error, loading} = useLoad<ClassPeople>(path + '/people');
  const {user, refresh, notify} = useAxon();
  const [modal, setModal] = useState('');
  const [code, setCode] = useState(initialCode || '');
  const t = useTask();
  const writable = room.can_manage && !room.archived;
  const teachers = data?.members.filter(item => item.role === 'teacher') ?? [];
  const learners = data?.members.filter(item => item.role === 'student') ?? [];
  const assigned = new Set(data?.teams.flatMap(team => team.students) ?? []);
  const choices = learners.filter(item => !assigned.has(item.id));

  const peopleList = (title: string, items: ClassPeople['members']) => <section className="class-panel class-roster">
    <h3>{title}</h3>
    {!items.length && <p className="muted">Aún no hay personas en esta lista.</p>}
    {items.map(person => <div className="class-person" key={person.id}>
      <span className="class-person-avatar" aria-hidden>{person.name[0]}</span>
      <span>{person.name}</span>
      {writable && person.id !== user.id && <button className="text-button" disabled={t.busy} onClick={() => {
        if (confirm('¿Quitar a esta persona de la clase?')) t.run(async () => {
          await api(path + '/members/' + person.id, {method: 'DELETE'}); refresh(); notify('Acceso retirado');
        });
      }}>Quitar</button>}
    </div>)}
  </section>;

  return <>
    <div className="class-section-heading"><h2>Personas de la clase</h2>{writable && <div className="button-row">
      <button className="secondary" onClick={() => setModal('teacher')}>Añadir profesor</button>
      <button className="primary" onClick={() => setModal('invite')}><Plus size={17}/> Invitar alumno</button>
    </div>}</div>
    <ErrorBox error={error || t.error}/>{loading && !data && <Loading/>}
    {room.can_manage&&<ClassAdmissionPanel path={path} archived={room.archived}/>}
    {writable && <section className="class-panel class-code">
      <div><h3><KeyRound size={18}/> Código de inscripción</h3>
        <p>{room.has_join_code ? 'La inscripción con código está abierta.' : 'La inscripción con código está cerrada.'}</p>
        {code && room.has_join_code && <div className="class-code-value"><code>{code}</code><button className="text-button" onClick={() => t.run(async () => {
          await navigator.clipboard.writeText(code); notify('Código copiado');
        })}>Copiar</button></div>}
      </div>
      <div className="button-row">
        <button className="secondary" disabled={t.busy} onClick={() => t.run(async () => {
          const result = await post<{join_code: string}>(path + '/join-code'); setCode(result.join_code); clearCode(); refresh();
        })}>{room.has_join_code ? 'Generar código nuevo' : 'Abrir inscripción'}</button>
        {room.has_join_code && <button className="text-button" disabled={t.busy} onClick={() => t.run(async () => {
          await api(path + '/join-code', {method: 'DELETE'}); setCode(''); clearCode(); refresh(); notify('Inscripción con código cerrada');
        })}>Cerrar inscripción</button>}
      </div>
    </section>}
    {data && <div className="class-roster-grid">
      {peopleList('Profesorado', teachers)}
      {peopleList(room.can_manage ? 'Alumnado inscrito' : 'Mi inscripción', learners)}
    </div>}
    {!!data && (writable || !!data.teams.length) && <section className="class-panel class-teams">
      <div className="class-section-heading"><h3>Equipos de trabajo</h3>
        {writable && <button className="secondary" disabled={choices.length < 2} onClick={() => setModal('team')}>Crear equipo</button>}
      </div>
      {data.teams.map(team => <p key={team.id}><strong>{team.name}</strong>
        {room.can_manage && <span> · {team.students.map(id => learners.find(learner => learner.id === id)?.name).filter(Boolean).join(', ')}</span>}</p>)}
      {!data.teams.length && <p className="muted">Para empezar un equipo, hacen falta al menos dos alumnos inscritos.</p>}
    </section>}
    {modal && <Modal title={modal === 'invite' ? 'Invitar alumno' : modal === 'teacher' ? 'Añadir profesor' : 'Crear equipo'}
      onClose={() => setModal('')}>
      <form onSubmit={event => {
        event.preventDefault();
        const body = new FormData(event.currentTarget);
        const destination = modal === 'invite' ? '/invitations' : modal === 'teacher' ? '/teachers' : '/teams';
        t.run(async () => {
          await post(path + destination, modal === 'team'
            ? {name: body.get('name'), students: body.getAll('students')}
            : {username: String(body.get('username')).trim().toLowerCase()});
          setModal(''); refresh(); notify(modal === 'invite' ? 'Invitación enviada en AXON' : 'Cambios guardados');
        });
      }}>
        {modal === 'team' ? <>
          <Field label="Nombre del equipo"><input name="name" maxLength={100} required/></Field>
          <fieldset className="class-team-choices"><legend>Selecciona al menos dos alumnos</legend>
            {choices.map(person => <label className="class-check" key={person.id}>
              <input type="checkbox" name="students" value={person.id}/>{person.name}
            </label>)}
          </fieldset>
        </> : <Field label="Usuario de AXON"><input name="username" required minLength={3} maxLength={100} autoCapitalize="off"/></Field>}
        <ErrorBox error={t.error}/>
        <button className="primary" disabled={t.busy}>{modal === 'invite' ? 'Enviar invitación' : 'Guardar'}</button>
      </form>
    </Modal>}
  </>;
}

function ClassCalendar({path, room}: {path: string; room: ClassRoom}) {
  const {data, error, loading} = useLoad<Event[]>(path + '/calendar');
  const {refresh, notify, navigate} = useAxon();
  const [open, setOpen] = useState(false);
  const [conflicts, setConflicts] = useState<string[]>([]);
  const t = useTask();
  const writable = room.can_manage && !room.archived;
  return <>
    <div className="class-section-heading"><h2>Calendario de la clase</h2><div className="button-row">
      <button className="secondary" onClick={() => navigate('calendar')}>Calendario general</button>
      {writable && <button className="primary" onClick={() => setOpen(true)}><Plus size={17}/> Programar evento</button>}
    </div></div>
    <ErrorBox error={error || t.error}/>{loading && !data && <Loading/>}
    {!!conflicts.length && <div className="class-panel" role="status">
      <strong>El evento coincide con estas citas de tu calendario</strong><p>{conflicts.join(', ')}</p>
    </div>}
    {data?.length === 0 && <Empty title="No hay citas de la clase">Las fechas de entrega y los exámenes publicados aparecerán aquí.</Empty>}
    <div className="class-event-list">{data?.map(event => <article key={event.id} className="class-event">
      <time dateTime={event.starts_at}><strong>{fmt(event.starts_at, {day: '2-digit'})}</strong>
        <small>{fmt(event.starts_at, {month: 'short'})}</small></time>
      <div><Badge tone={event.kind === 'exam' ? 'amber' : 'green'}>
        {event.status === 'cancelled' ? 'Cancelado' : ({exam: 'Examen', assignment: 'Entrega', session: 'Sesión', event: 'Evento'})[event.kind] || 'Evento'}
      </Badge>
        <h3>{event.title}</h3><p>{fmt(event.starts_at, {dateStyle: 'medium', timeStyle: 'short'})}{event.description && ' · ' + event.description}</p>
      </div>
      {writable && event.status !== 'cancelled' && !event.activity_id && <button className="text-button" disabled={t.busy} onClick={() => {
        if (confirm('¿Cancelar este evento para toda la clase?')) t.run(async () => {
          await api(path + '/calendar/' + event.id, {method: 'DELETE'}); refresh(); notify('Evento cancelado');
        });
      }}>Cancelar evento</button>}
    </article>)}</div>
    {open && <Modal title="Programar evento" onClose={() => setOpen(false)}>
      <form onSubmit={event => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        t.run(async () => {
          const result = await post<{conflicts: string[]}>(path + '/calendar', {
            title: form.get('title'), description: form.get('description'), kind: form.get('kind'),
            starts_at: madridIso(String(form.get('starts'))), ends_at: madridIso(String(form.get('ends'))),
          });
          setConflicts(result.conflicts); setOpen(false); refresh(); notify('Evento añadido al calendario');
        });
      }}>
        <Field label="Título"><input name="title" maxLength={160} required/></Field>
        <Field label="Tipo"><select name="kind"><option value="event">Evento</option><option value="session">Sesión</option><option value="exam">Examen</option></select></Field>
        <div className="form-grid"><Field label="Inicio (Madrid)"><input type="datetime-local" name="starts" required/></Field>
          <Field label="Fin (Madrid)"><input type="datetime-local" name="ends" required/></Field></div>
        <Field label="Descripción"><textarea name="description" rows={3} maxLength={2500}/></Field>
        <ErrorBox error={t.error}/><button className="primary" disabled={t.busy}>Publicar evento</button>
      </form>
    </Modal>}
  </>;
}

const assistantModes = [
  ['explain', 'Explicar un tema'], ['review', 'Preparar un repaso'], ['practice', 'Crear ejercicios de práctica'],
  ['pending', 'Ver entregas pendientes'], ['plan', 'Plan de estudio'],
];
const staffModes = [
  ['activity', 'Borrador de actividad'], ['quiz', 'Borrador de cuestionario'], ['material', 'Material educativo'],
  ['rubric', 'Rúbrica'], ['summary', 'Resumen de materiales'], ['conflicts', 'Buscar fechas que coinciden'],
  ['unit', 'Unidad didáctica'], ['level', 'Ejercicios por dificultad'], ['feedback', 'Comentario de corrección'],
];
type AssistReply = {
  content: string; engine: string; draft: boolean;
  citations: {document_id: string; title: string; location: string}[];
};

function ClassAssistant({path, room, close, onDraft}: {
  path: string; room: ClassRoom; close: () => void; onDraft: (text: string) => void;
}) {
  const [mode, setMode] = useState('explain');
  const [answer, setAnswer] = useState<AssistReply | null>(null);
  const t = useTask();
  const structured = mode === 'pending' || mode === 'conflicts';
  const options = room.can_manage ? [...assistantModes, ...staffModes] : assistantModes;
  return <Modal title="Preguntar a AXON" onClose={close} wide>
    <form onSubmit={event => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      t.run(async () => {
        setAnswer(null);
        setAnswer(await post<AssistReply>(path + '/assist', {
          mode, prompt: structured ? options.find(item => item[0] === mode)?.[1] : form.get('prompt'),
          use_memory: form.has('memory'),
        }));
      });
    }}>
      <Field label="¿En qué quieres ayuda?"><select value={mode} disabled={t.busy} onChange={event => {
        setMode(event.target.value); setAnswer(null);
      }}>
        {options.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></Field>
      {!structured && <><Field label="Tu pregunta o indicaciones">
        <textarea name="prompt" rows={4} minLength={3} maxLength={1600} required placeholder="Por ejemplo, explícame un concepto del primer tema"/>
      </Field><label className="class-check"><input name="memory" type="checkbox"/> Incluir mis recuerdos pertinentes</label></>}
      <ErrorBox error={t.error}/>
      <button className="primary" disabled={t.busy}><Sparkles size={17}/> {t.busy ? 'Consultando a AXON…' : 'Consultar'}</button>
    </form>
    {answer && <section className="class-panel class-ai-answer" aria-live="polite">
      <div className="class-section-heading"><h3>Respuesta de AXON</h3>
        {answer.draft && <Badge tone="amber">Para revisión</Badge>}</div>
      <p className="pre-wrap">{answer.content}</p>
      {!!answer.citations.length && <ul className="class-citations">
        {answer.citations.map(item => <li key={item.document_id + item.location}>
          <a href={'/api/documents/' + item.document_id + '/download'}>{item.title}</a> · {item.location}
        </li>)}
      </ul>}
      {room.can_manage && !room.archived && answer.engine === 'ollama' &&
        ['activity', 'quiz', 'level', 'unit'].includes(mode) && <button className="secondary"
          onClick={() => onDraft(answer.content)}>Revisar como borrador de actividad</button>}
    </section>}
  </Modal>;
}
