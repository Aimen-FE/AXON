import {Empty,ErrorBox,Loading,PageTitle,useAxon,useLoad} from './core';

interface Organization {
  center:string;
  fictional:boolean;
  organization:{direction?:string;studies?:string;secretary?:string;departments?:{name:string;coordinator:string}[]};
  tutors:{group:string;teacher:string;office_hour:string}[];
  break:{starts:string;ends:string}|null;
}
export default function OrganizationView(){
  const {data,error}=useLoad<Organization>('/education/organization');
  const {data:overview}=useLoad<{classes:number;pending_reviews:number|null}>('/education/overview');
  const {user,navigate}=useAxon();
  return <><PageTitle title="Organización educativa">Personas, tutorías y estructura del entorno de demostración.</PageTitle>
    <ErrorBox error={error}/>{!data?<Loading/>:<>
      <section className="card padded"><h2>{data.center}</h2><p>{overview?.classes??'—'} clases autorizadas para tu perfil.</p>
        {data.break&&<p>Recreo de demostración de {data.break.starts} a {data.break.ends}.</p>}
        {user.role==='admin'&&<><dl className="args">{([['Dirección','direction'],['Jefatura de estudios','studies'],['Secretaría','secretary']] as const).map(([label,key])=><div key={key}><dt>{label}</dt><dd>{data.organization[key]||'Sin asignar'}</dd></div>)}</dl>
          <h3>Departamentos didácticos</h3>{data.organization.departments?.map(item=><p key={item.name}>{item.name} · {item.coordinator}</p>)}
          <button className="secondary" onClick={()=>navigate('admin')}>Gestionar grupos y asignaciones</button></>}
      </section>
      <section className="card padded"><h2>Tutorías</h2>{data.tutors.length?data.tutors.map(tutor=><article key={tutor.group}><h3>{tutor.group}</h3><p>{tutor.teacher} · {tutor.office_hour}</p></article>):<Empty title="Sin tutorías asignadas"/>}</section>
    </>}</>;
}
