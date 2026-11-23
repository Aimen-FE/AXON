import {FileText} from 'lucide-react';
import {api} from './api';
import {ErrorBox, Field, Modal, useAxon, useTask} from './core';
import {FILE_TYPES, type ClassFile, type ClassTopic} from './class-types';

export function FileLink({file, href}: {file: ClassFile; href?: string}) {
  return <a className="class-file-link" href={href ?? '/api/documents/' + file.id + '/download'}>
    <FileText size={19}/>
    <span><strong>{file.title}</strong><small>{file.filename} · {new Intl.NumberFormat('es-ES', {maximumFractionDigits: 1}).format(file.size / 1024)} kB</small></span>
  </a>;
}

export function FileForm({path, topics, activityId, close}: {
  path: string; topics?: ClassTopic[]; activityId?: string; close: () => void;
}) {
  const {refresh, notify} = useAxon();
  const t = useTask();
  return <Modal title={activityId ? 'Adjuntar a la actividad' : 'Subir material'} onClose={close}>
    <form onSubmit={event => {
      event.preventDefault();
      const body = new FormData(event.currentTarget);
      if (!body.get('topic_id')) body.delete('topic_id');
      if (activityId) body.append('activity_id', activityId);
      t.run(async () => {await api(path, {method: 'POST', body}); refresh(); close(); notify('Archivo adjuntado')});
    }}>
      <Field label="Título"><input name="title" required maxLength={180}/></Field>
      {topics && <Field label="Tema"><select name="topic_id"><option value="">Sin tema</option>
        {topics.map(topic => <option key={topic.id} value={topic.id}>{topic.name}</option>)}
      </select></Field>}
      <Field label="Archivo"><input type="file" name="file" accept={FILE_TYPES} required/></Field>
      <ErrorBox error={t.error}/><button className="primary" disabled={t.busy}>{t.busy ? 'Subiendo…' : 'Subir archivo'}</button>
    </form>
  </Modal>;
}
