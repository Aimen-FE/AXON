import {publicAsset} from './server-connection';
import {lazy,Suspense,useEffect,useRef,useState,type ReactNode} from 'react';
import {LayoutDashboard,MessageSquare,Brain,CalendarDays,Clock3,BookOpen,GraduationCap,ClipboardList,Files,Bell,UserRound,Settings,Users,ShieldCheck,DoorOpen,ChartNoAxesCombined,LogOut,Menu,Sun,Moon,ArrowUpRight,Search,Check,type LucideIcon} from 'lucide-react';
import {useNavigationLanguage,englishNavigation} from './i18n';
import {api,post,setCsrf,setUnauthorized,roleLabel} from './api';
import type {User,Academic,System,Action,ToolResult} from './types';
import {AxonContext,Modal,ActionPanel,Loading,ErrorBox} from './core';

import {GuestQuota,GuestStudy} from './guest-ui';
import {TeacherSessionInfo} from './teacher-ui';
import {Login} from './login';
import {InstallAxon} from './pwa';

const DashboardView = lazy(() => import('./personal').then(module => ({default: module.DashboardView})));
const ProfileView = lazy(() => import('./personal').then(module => ({default: module.ProfileView})));
const SettingsView = lazy(() => import('./personal').then(module => ({default: module.SettingsView})));
const NotificationsView = lazy(() => import('./personal').then(module => ({default: module.NotificationsView})));
const TeacherView = lazy(() => import('./personal').then(module => ({default: module.TeacherView})));
const AutomationsView = lazy(() => import('./operations-ui').then(module => ({default: module.AutomationsView})));
const MaterialsView = lazy(() => import('./operations-ui').then(module => ({default: module.MaterialsView})));
const UniversalSearchView = lazy(() => import('./operations-ui').then(module => ({default: module.UniversalSearchView})));
const OperationsView = lazy(() => import('./operations-ui').then(module => ({default: module.OperationsView})));
const MathView = lazy(() => import('./agent-ui').then(module => ({default: module.MathView})));
const ExtensionsView = lazy(() => import('./agent-ui').then(module => ({default: module.ExtensionsView})));
const ChatView = lazy(() => import('./conversation').then(module => ({default: module.ChatView})));
const MemoryView = lazy(() => import('./conversation').then(module => ({default: module.MemoryView})));
const CalendarView = lazy(() => import('./academic').then(module => ({default: module.CalendarView})));
const ExamsView = lazy(() => import('./academic').then(module => ({default: module.ExamsView})));
const TasksView = lazy(() => import('./academic').then(module => ({default: module.TasksView})));
const ScheduleView = lazy(() => import('./academic').then(module => ({default: module.ScheduleView})));
const SubjectsView = lazy(() => import('./academic').then(module => ({default: module.SubjectsView})));
const DocumentsView = lazy(() => import('./management').then(module => ({default: module.DocumentsView})));
const BathroomView = lazy(() => import('./management').then(module => ({default: module.BathroomView})));
const ReportsView = lazy(() => import('./management').then(module => ({default: module.ReportsView})));
const AdminView = lazy(() => import('./management').then(module => ({default: module.AdminView})));
const SetupAccount = lazy(() => import('./learning').then(module => ({default: module.SetupAccount})));
const AcademicWorkspace = lazy(() => import('./learning').then(module => ({default: module.AcademicWorkspace})));
const PersonalScheduleView = lazy(() => import('./learning').then(module => ({default: module.PersonalScheduleView})));
const CalculatorView = lazy(() => import('./learning').then(module => ({default: module.CalculatorView})));
const StudyView = lazy(() => import('./learning').then(module => ({default: module.StudyView})));
const OrganizationView=lazy(()=>import('./organization'));
const ClassesView = lazy(() => import('./classes'));
const IntegrationView = lazy(() => import('./learning').then(module => ({default: module.IntegrationView})));
const ResearchView = lazy(() => import('./learning').then(module => ({default: module.ResearchView})));
const AtlasView = lazy(() => import('./atlas-ui').then(module => ({default: module.AtlasView})));
const ProvidersView = lazy(() => import('./providers-ui').then(module => ({default: module.ProvidersView})));
const RemoteView = lazy(() => import('./remote-ui').then(module => ({default: module.RemoteView})));

const NAV:{section:string;items:{id:string;name:string;icon:LucideIcon;roles?:string[]}[]}[]=[
 {section:'TU ESPACIO',items:[{id:'dashboard',name:'Panel principal',icon:LayoutDashboard},{id:'chat',name:'Asistente AXON',icon:MessageSquare},{id:'memory',name:'Memoria',icon:Brain}]},
 {section:'APRENDIZAJE',items:[{id:'classes',name:'Clases',icon:GraduationCap},{id:'calendar',name:'Calendario',icon:CalendarDays},{id:'schedules',name:'Horarios',icon:Clock3},{id:'subjects',name:'Asignaturas',icon:BookOpen},{id:'exams',name:'Exámenes',icon:GraduationCap},{id:'tasks',name:'Tareas',icon:ClipboardList},{id:'documents',name:'Documentos',icon:Files},{id:'knowledge',name:'Fuentes y temario',icon:BookOpen},{id:'study',name:'Estudio y planificación',icon:Brain},{id:'calculator',name:'Calculadora de notas',icon:GraduationCap},{id:'math',name:'Matemáticas',icon:GraduationCap},{id:'automations',name:'Automatizaciones',icon:Clock3},{id:'materials',name:'Materiales',icon:Files},{id:'search',name:'Buscar en tu espacio',icon:Search},{id:'extensions',name:'Herramientas del agente',icon:Settings},{id:'research',name:'Investigación pública',icon:Search}]},
 {section:'CENTRO',items:[{id:'organization',name:'Organización educativa',icon:Users},{id:'atlas',name:'Núcleo de AXON',icon:Brain},{id:'providers',name:'Modelos y recursos',icon:Settings},{id:'teacher',name:'Panel de profesor',icon:Users,roles:['teacher','admin']},{id:'bathroom',name:'Registro de salidas',icon:DoorOpen,roles:['teacher','admin']},{id:'reports',name:'Informes',icon:ChartNoAxesCombined,roles:['admin']},{id:'remote',name:'Demostración pública',icon:ShieldCheck,roles:['admin']},{id:'operations',name:'Estado y recuperación',icon:Settings,roles:['admin']},{id:'admin',name:'Administración',icon:ShieldCheck,roles:['admin']}]},
 {section:'INTEGRACIONES',items:[{id:'integrations',name:'Integraciones',icon:Settings}]}
];
const names:Record<string,string>=Object.fromEntries(NAV.flatMap(s=>s.items.map(i=>[i.id,i.name])).concat([['profile','Mi perfil'],['settings','Configuración'],['notifications','Notificaciones']]));

export default function App(){
 const [user,setUser]=useState<User|null>(null),[boot,setBoot]=useState(true);
 useEffect(()=>{setUnauthorized(()=>{setUser(null);setCsrf('')});api<{user:User;csrf_token:string}>('/auth/me').then(r=>{setUser(r.user);setCsrf(r.csrf_token)}).catch(()=>{}).finally(()=>setBoot(false))},[]);
 if(boot)return <Loading/>;
 const setup=location.hash.startsWith('#setup=')?location.hash.slice(7):'';
 if(setup)return <Suspense fallback={<Loading/>}><SetupAccount token={setup} onLogin={setUser}/></Suspense>;
 return user?<Workspace key={user.id} user={user} setUser={setUser}/>:<Login onLogin={setUser}/>;
}

function Workspace({user,setUser}:{user:User;setUser:(u:User|null)=>void}){
 const language=useNavigationLanguage();const navName=(id:string,fallback:string)=>language==='en'?(englishNavigation[id]||fallback):fallback;
 const [academic,setAcademic]=useState<Academic|null>(null),[system,setSystem]=useState<System|null>(null),[actions,setActions]=useState<Action[]>([]),[revision,setRevision]=useState(0),[error,setError]=useState('');
 const [page,setPage]=useState(location.hash.slice(1)||(user.temporary_guest?'chat':'dashboard')),[mobile,setMobile]=useState(false),[toast,setToast]=useState<{message:string;error:boolean}|null>(null),[proposal,setProposal]=useState<ToolResult|null>(null);
 const [theme,setTheme]=useState(localStorage.getItem('axon-theme')||user.preferences?.theme||'dark');
 useEffect(()=>{const listener=(e:Event)=>setTheme((e as CustomEvent<string>).detail);addEventListener('axon-theme',listener);return()=>removeEventListener('axon-theme',listener)},[]);
 const sidebar = useRef<HTMLElement>(null);
 const menuButton = useRef<HTMLButtonElement>(null);
 const main = useRef<HTMLElement>(null);
 const [smallScreen, setSmallScreen] = useState(() => matchMedia('(max-width: 760px)').matches);
 const drawerOpen = smallScreen && mobile;

 useEffect(() => {
  const breakpoint = matchMedia('(max-width: 760px)');
  const update = () => { setSmallScreen(breakpoint.matches); if (!breakpoint.matches) setMobile(false); };
  breakpoint.addEventListener('change', update);
  return () => breakpoint.removeEventListener('change', update);
 }, []);
 useEffect(() => {
  if (!drawerOpen) return;

  const frame = requestAnimationFrame(() => sidebar.current?.querySelector<HTMLElement>('button[aria-current="page"], .brand')?.focus({preventScroll:true}));
  const oldOverflow = document.body.style.overflow;
  document.body.style.overflow = 'hidden';
  const keyboard = (event: KeyboardEvent) => {
   if (event.key === 'Escape') { setMobile(false); return; }
   if (event.key !== 'Tab' || !sidebar.current) return;
   const controls = [...sidebar.current.querySelectorAll<HTMLElement>('a[href], button:not([disabled])')].filter(item => item.getClientRects().length);
   const first = controls[0], last = controls[controls.length - 1];
   if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
   else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
  };
  document.addEventListener('keydown', keyboard);
  return () => {
   cancelAnimationFrame(frame);
   document.body.style.overflow = oldOverflow;
   document.removeEventListener('keydown', keyboard);
   requestAnimationFrame(() => menuButton.current?.focus({preventScroll:true}));
  };
 }, [drawerOpen]);
 const navigate=(p:string)=>{location.hash=p;setPage(p);setMobile(false)};
 useEffect(()=>{const handler=()=>{setPage(location.hash.slice(1)||(user.temporary_guest?'chat':'dashboard'));setMobile(false)};addEventListener('hashchange',handler);return()=>removeEventListener('hashchange',handler)},[]);
 useEffect(()=>{let active=true;api<Academic>('/academic').then(d=>{if(active){setAcademic(d);setError('')}}).catch(e=>{if(active)setError(e.message)});api<Action[]>('/actions').then(a=>{if(active)setActions(a)}).catch(()=>{});return()=>{active=false}},[revision]);
 useEffect(()=>{api<System>('/system').then(setSystem).catch(()=>{})},[]);
 useEffect(()=>{const media=matchMedia('(prefers-color-scheme: dark)');const update=()=>document.documentElement.dataset.theme=theme==='system'?(media.matches?'dark':'light'):theme;update();media.addEventListener('change',update);localStorage.setItem('axon-theme',theme);return()=>media.removeEventListener('change',update)},[theme]);
 useEffect(()=>{if(!toast)return;const timer=setTimeout(()=>setToast(null),6000);return()=>clearTimeout(timer)},[toast]);
 const refresh=()=>setRevision(v=>v+1);const notify=(message:string,error=false)=>setToast({message,error});
 const propose=async(tool:string,args:unknown)=>{const r=await post<ToolResult>('/tools/call',{tool,arguments:args});refresh();if(r.action)setProposal(r);else notify('Operación guardada correctamente')};
 const logout=async()=>{try{await post(user.demo_teacher?'/teacher-demo/end':user.temporary_guest?'/guest/end':'/auth/logout');setCsrf('');setUser(null)}catch(e){notify((e as Error).message,true)}};
 useEffect(()=>{const onKey=(e:KeyboardEvent)=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();navigate('search')}};addEventListener('keydown',onKey);return()=>removeEventListener('keydown',onKey)},[]);
 const toggleTheme=()=>setTheme(document.documentElement.dataset.theme==='dark'?'light':'dark');
 const sectionPage=page.startsWith('classes/')?'classes':page;
 const views:Record<string,ReactNode>={organization:<OrganizationView/>,classes:<ClassesView route={page}/>,remote:<RemoteView/>,providers:<ProvidersView/>,atlas:<AtlasView/>,dashboard:<DashboardView/>,chat:<ChatView/>,memory:<MemoryView/>,calendar:<CalendarView/>,schedules:user.has_academic_profile?<PersonalScheduleView/>:<ScheduleView/>,subjects:user.has_academic_profile?<AcademicWorkspace/>:<SubjectsView/>,knowledge:<AcademicWorkspace/>,study:user.temporary_guest?<GuestStudy/>:<StudyView/>,calculator:<CalculatorView/>,research:<ResearchView/>,math:<MathView/>,extensions:<ExtensionsView/>,automations:<AutomationsView/>,materials:<MaterialsView/>,search:<UniversalSearchView/>,operations:<OperationsView/>,integrations:<IntegrationView/>,exams:<ExamsView/>,tasks:<TasksView/>,documents:<DocumentsView/>,notifications:<NotificationsView/>,profile:<ProfileView/>,settings:<SettingsView/>,teacher:<TeacherView/>,bathroom:<BathroomView/>,reports:<ReportsView/>,admin:<AdminView/>};
 const guestPages=['chat','memory','calendar','schedules','exams','tasks','documents','atlas','study','math'];
 const allowed=(!user.temporary_guest||guestPages.includes(sectionPage))&&!((['reports','admin','operations','remote'].includes(page)&&user.role!=='admin')||(['teacher','bathroom'].includes(page)&&user.role==='student'));
 if(!academic)return <div className="startup"><Loading/><ErrorBox error={error}/>{error&&<button className="primary" onClick={refresh}>Reintentar</button>}</div>;
 return <AxonContext.Provider value={{user,academic,system,actions,revision,refresh,notify,propose,navigate,setUser}}><div className="app-shell"><a className="skip-link" href="#main-content" inert={drawerOpen} onClick={event=>{event.preventDefault();main.current?.focus()}}>Saltar al contenido</a><div aria-hidden="true" className={'sidebar-overlay '+(drawerOpen?'open':'')} onClick={()=>setMobile(false)}/><aside id="axon-sidebar" ref={sidebar} inert={smallScreen&&!drawerOpen} className={'sidebar '+(drawerOpen?'open':'')}><a className="brand" href={user.temporary_guest?'#chat':'#dashboard'} onClick={()=>navigate(user.temporary_guest?'chat':'dashboard')}><img src={publicAsset('icon.svg')} alt=""/><span>AXON<span className="brand-dot">.</span></span></a><div className="school-mark"><span className="school-avatar"><GraduationCap size={20}/></span><div><strong>{academic.center.name.replace(' · Demostración','')}</strong><small>{academic.center.town} · {academic.years[0]?.name}</small></div></div><nav aria-label="Navegación principal">{NAV.map(section=><div className="nav-section" key={section.section}><p>{section.section}</p>{section.items.filter(i=>(!i.roles||i.roles.includes(user.role))&&(!user.temporary_guest||guestPages.includes(i.id))).map(i=><button key={i.id} className={sectionPage===i.id?'active':''} onClick={()=>navigate(i.id)} aria-current={sectionPage===i.id?'page':undefined}><i.icon size={18}/><span>{navName(i.id,i.name)}</span>{i.id==='chat'&&<span className="nav-ai">IA</span>}</button>)}</div>)}</nav><div className="sidebar-bottom">{user.temporary_guest?<GuestQuota/>:<><button onClick={()=>navigate('notifications')}><Bell size={18}/>Notificaciones</button><button onClick={()=>navigate('settings')}><Settings size={18}/>Configuración</button><button className="user-card" onClick={()=>navigate('profile')}><span className="avatar">{user.display_name.slice(0,1)}</span><span><strong>{user.display_name}</strong><small>{roleLabel[user.role]} · {user.is_demo?'Demo':'Privado'}</small></span><ArrowUpRight size={16}/></button>{user.demo_teacher&&<TeacherSessionInfo/>}</>}</div></aside><div className="workspace" inert={drawerOpen}><header className="topbar"><div className="row"><button ref={menuButton} className="icon-button mobile-menu" aria-label="Abrir navegación" aria-expanded={drawerOpen} aria-controls="axon-sidebar" onClick={()=>setMobile(true)}><Menu size={22}/></button><span className="breadcrumb">Mi espacio <span>/</span> <strong>{navName(sectionPage,names[sectionPage]||'AXON')}</strong></span></div><div className="top-actions"><span className="local-state"><span/>{user.demo_teacher?roleLabel[user.role]+' · demostración':user.temporary_guest?'Demo pública':system?.remote_demo?'Demostración protegida':'Tu centro'}</span>{!user.temporary_guest&&<button className="icon-button" aria-label="Buscar en tu espacio" onClick={()=>navigate('search')}><Search size={19}/></button>}<button className="icon-button" aria-label="Cambiar entre modo claro y oscuro" onClick={toggleTheme}>{theme==='dark'?<Sun size={19}/>:<Moon size={19}/>}</button><InstallAxon compact/><button className="icon-button" aria-label="Cerrar sesión" onClick={logout}><LogOut size={19}/></button></div></header><div className="demo-strip"><ShieldCheck size={14}/><span>{user.is_demo?'Demostración · Actividad académica ficticia':roleLabel[user.role]+' · '+academic.center.name}</span><span className="demo-strip-right">{user.demo_teacher?'Tu centro ficticio está separado de los demás visitantes.':user.temporary_guest?'Sesión temporal. Usa datos inventados.':'Tu memoria y tus conversaciones son privadas.'}</span></div><main className={'content '+(page==='chat'?'chat-content':'')} id="main-content" ref={main} tabIndex={-1}><div key={sectionPage} className="view-enter"><Suspense fallback={<Loading/>}>{allowed?(views[sectionPage]||<DashboardView/>):<ErrorBox error="Esta sección no está disponible para tu perfil."/>}</Suspense></div></main><footer className="app-footer"><span>AXON</span><span>Europe/Madrid · Versión 0.7.0</span></footer></div>{toast&&<div className={'toast '+(toast.error?'danger':'')} role="status">{toast.error?<ShieldCheck size={18}/>:<Check size={18}/>}<span>{toast.message}</span></div>}{proposal?.action&&<Modal title="Revisa la propuesta" onClose={()=>setProposal(null)}><ActionPanel action={proposal.action} conflicts={proposal.conflicts} onDone={()=>setProposal(null)}/></Modal>}</div></AxonContext.Provider>
}
