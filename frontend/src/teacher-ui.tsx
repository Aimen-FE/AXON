import {publicAsset} from './server-connection';
import {InstallAxon} from './pwa';
import {useState} from 'react';
import {ArrowRight,ShieldCheck,Loader2,GraduationCap} from 'lucide-react';
import {post,setCsrf} from './api';
import {useAxon,useLoad,ErrorBox} from './core';
import type {User} from './types';

export function TeacherWelcome({onLogin}:{onLogin:(u:User)=>void}){
 const [role,setRole]=useState('teacher');
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 const start=async()=>{setBusy(true);setError('');try{const result=await post<{user:User;csrf_token:string}>('/teacher-demo/start',{role});setCsrf(result.csrf_token);location.hash='dashboard';onLogin(result.user)}catch(e){setError((e as Error).message)}finally{setBusy(false)}};
 return <div className="login-layout"><section className="login-brand"><a className="brand" href="/"><img src={publicAsset('icon.svg')} alt=""/><span>AXON<span className="brand-dot">.</span></span></a><div className="login-intro"><h1>AXON, al completo.</h1><p>Un espacio para enseñar, aprender y organizar el día a día del centro.</p><p>Prueba el asistente con Ollama, la memoria, los documentos, el tutor y las herramientas académicas.</p></div><p className="login-foot"><ShieldCheck size={16}/>Prototipo educativo independiente.</p></section><main className="login-main"><div className="login-form"><GraduationCap size={32}/><h2>Prueba el Centro Educativo Nébula</h2><p>Entra sin correo ni contraseña. Tendrás tu propio centro de ejemplo, con alumnado, horarios, exámenes y documentos ficticios.</p><label>Perfil de demostración<select value={role} onChange={event=>setRole(event.target.value)}><option value="teacher">Profesor</option><option value="student">Alumno</option><option value="admin">Administrador ficticio</option></select></label><button className="primary full" disabled={busy} onClick={start}>{busy&&<Loader2 size={18} className="spin"/>}Entrar en Nébula<ArrowRight size={18}/></button><ErrorBox error={error}/><p>Tus conversaciones, archivos y cambios estarán separados de los demás visitantes. Las operaciones académicas se revisan antes de confirmarlas.</p><p className="fine-print">La sesión dura 24 horas; el enlace continúa activo mientras funcionen el ordenador y los servicios. Usa datos inventados. Puedes cambiar de perfil dentro de tu centro ficticio.</p><p className="login-school">Centro Educativo Nébula · Villa Prisma<br/>Institución y personas inventadas para la demostración.</p><InstallAxon/></div></main></div>
}

export function TeacherSessionInfo(){
 const {user,setUser,navigate,notify}=useAxon();const {data}=useLoad<{expires_at:string;queries_remaining_this_hour:number}>('/teacher-demo/status');
 if(!user.demo_teacher)return null;
 return <div className="teacher-session-note"><label className="fine-print">Perfil ficticio<select aria-label="Cambiar perfil de demostración" value={user.role} onChange={async event=>{
   try{const result=await post<{user:User;csrf_token:string}>('/teacher-demo/perspective',{role:event.target.value});setCsrf(result.csrf_token);setUser(result.user);navigate('classes')}catch(error){notify((error as Error).message,true)}
 }}><option value="teacher">Profesor</option><option value="student">Alumno</option><option value="admin">Administrador ficticio</option></select></label><p className="fine-print">Espacio ficticio propio<br/>{data?`${data.queries_remaining_this_hour} consultas disponibles esta hora · sesión hasta ${new Date(data.expires_at).toLocaleString('es-ES',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})}`:'Sesión ficticia de 24 horas'}</p></div>
}
