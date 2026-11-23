import {useState} from 'react';
import {api, post} from './api';
import {ErrorBox, Field, useAxon, useLoad, useTask} from './core';

export function ClassAdmissionPanel({path, archived}: {path: string; archived: boolean}) {
  const {user,refresh,notify}=useAxon();
  const config=useLoad<{teacher_invitations:boolean;review_codes:boolean;code_limit:number}>(path+'/admission');
  const requests=useLoad<{id:string;name:string}[]>(path+'/requests');
  const invitations=useLoad<{id:string;name:string;expires_at:string}[]>(path+'/invitations');
  const t=useTask();
  return <section className="class-panel class-admissions">
    <h3>Inscripciones e invitaciones</h3>
    <ErrorBox error={config.error||requests.error||invitations.error||t.error}/>
    {user.role==='admin'&&config.data&&!archived&&<form key={JSON.stringify(config.data)} onSubmit={event=>{
      event.preventDefault();const f=new FormData(event.currentTarget);
      t.run(async()=>{await api(path+'/admission',{method:'PUT',body:JSON.stringify({teacher_invitations:f.has('invitations'),review_codes:f.has('review'),code_limit:Number(f.get('limit'))})});refresh();notify('Admisión actualizada')});
    }}>
      <label className="class-check"><input name="invitations" type="checkbox" defaultChecked={config.data.teacher_invitations}/>Permitir invitaciones del profesorado</label>
      <label className="class-check"><input name="review" type="checkbox" defaultChecked={config.data.review_codes}/>Revisar las solicitudes por código</label>
      <Field label="Usos máximos del código"><input name="limit" type="number" min={1} max={200} defaultValue={config.data.code_limit}/></Field>
      <button className="secondary" disabled={t.busy}>Guardar admisión</button>
    </form>}
    {config.data&&<p className="fine-print">Los códigos caducan a los siete días y admiten {config.data.code_limit} inscripciones.</p>}
    {requests.data?.map(request=><div className="class-person" key={request.id}>
      <span>{request.name}</span>{!archived&&[true,false].map(approve=><button key={String(approve)} className="text-button" disabled={t.busy} onClick={()=>t.run(async()=>{
        await post(path+'/requests/'+request.id,{approve});refresh();notify(approve?'Inscripción aprobada':'Solicitud rechazada');
      })}>{approve?'Aprobar':'Rechazar'}</button>)}
    </div>)}
    {invitations.data?.map(invitation=><div className="class-person" key={invitation.id}><span>Invitación a {invitation.name}</span>
      {!archived&&<button className="text-button" disabled={t.busy} onClick={()=>t.run(async()=>{await api(path+'/invitations/'+invitation.id,{method:'DELETE'});refresh();notify('Invitación revocada')})}>Revocar</button>}
    </div>)}
  </section>;
}

export function ClassEvaluationPanel({path, writable}:{path:string;writable:boolean}) {
  const {data,error}=useLoad<{weights:Record<string,number>}>(path+'/evaluation');
  const {refresh,notify}=useAxon();const t=useTask();
  const labels:Record<string,string>={activities:'Actividades',exams:'Exámenes',projects:'Proyectos',participation:'Participación'};
  return <section className="class-panel"><h3>Ponderaciones de demostración</h3><ErrorBox error={error||t.error}/>
    {data&&<form key={JSON.stringify(data)} onSubmit={event=>{
      event.preventDefault();const f=new FormData(event.currentTarget);
      t.run(async()=>{await api(path+'/evaluation',{method:'PUT',body:JSON.stringify({weights:Object.fromEntries(Object.keys(labels).map(key=>[key,Number(f.get(key))]))})});refresh();notify('Ponderaciones actualizadas')});
    }}><div className="form-grid">{Object.entries(labels).map(([key,label])=><Field key={key} label={label+' (%)'}>
      <input name={key} type="number" min={0} max={100} required defaultValue={data.weights[key]??0} readOnly={!writable}/>
    </Field>)}</div>{writable&&<button className="secondary" disabled={t.busy}>Guardar ponderaciones</button>}</form>}
    <p className="fine-print">Son criterios configurables de la simulación educativa.</p>
  </section>;
}

export function ClassSolutionPanel({path,writable}:{path:string;writable:boolean}) {
  const {data,error}=useLoad<{content:string}>(path+'/solution');const {notify,refresh}=useAxon();const [editing,setEditing]=useState(false);const t=useTask();
  return <details className="class-panel"><summary>Guía interna de corrección del profesorado</summary><ErrorBox error={error||t.error}/>
    {data&&<>{editing?<form onSubmit={event=>{event.preventDefault();const content=new FormData(event.currentTarget).get('content');t.run(async()=>{await api(path+'/solution',{method:'PUT',body:JSON.stringify({content})});setEditing(false);refresh();notify('Guía guardada')})}}>
      <Field label="Criterios y solución interna"><textarea name="content" rows={5} required maxLength={6000} defaultValue={data.content}/></Field><button className="secondary" disabled={t.busy}>Guardar guía</button>
    </form>:<p className="pre-wrap">{data.content||'Todavía no hay una guía interna.'}</p>}
    {writable&&!editing&&<button className="text-button" onClick={()=>setEditing(true)}>Editar guía</button>}</>}
  </details>;
}
