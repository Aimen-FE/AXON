import {publicAsset} from './server-connection';
import {useEffect, useState, type FormEvent} from 'react';
import {ArrowRight, BookOpen, Eye, EyeOff, GraduationCap, Loader2, Settings2} from 'lucide-react';
import {api, post, setCsrf} from './api';
import {ErrorBox, Loading} from './core';
import {GuestWelcome} from './guest-ui';
import {TeacherWelcome} from './teacher-ui';
import {InstallAxon} from './pwa';
import type {User} from './types';

type EntryInformation = {
  full_demo?: boolean;
  public_demo?: boolean;
  remote_demo?: boolean;
  setup_required?: boolean;
};

export function Login({onLogin}: {onLogin: (user: User) => void}) {
  const [info, setInfo] = useState<EntryInformation | null>(null);
  const [reload, setReload] = useState(0);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [invitation, setInvitation] = useState(() => new URLSearchParams(location.hash.slice(1)).get('invite') || '');
  const [visible, setVisible] = useState(false);
  const [waiting, setWaiting] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    let mounted = true;
    api<EntryInformation>('/public/info')
      .then(result => { if (mounted) setInfo(result); })
      .catch(reason => { if (mounted) setError(reason.message); });
    return () => { mounted = false; };
  }, [reload]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (waiting) return;
    setWaiting(true);
    setError('');
    setNotice('');
    try {
      if (invitation) {
        if (password !== confirmation) throw new Error('Las contraseñas no coinciden.');
        const result = await post<{username: string; message: string}>('/remote/accept', {token: invitation, password});
        setUsername(result.username);
        setInvitation('');
        setConfirmation('');
        setPassword('');
        history.replaceState(null, '', location.pathname + location.search);
        setNotice(result.message);
        return;
      }
      const result = await post<{user: User; csrf_token: string}>('/auth/login', {username, password});
      setCsrf(result.csrf_token);
      onLogin(result.user);
    } catch (reason) {
      setError((reason as Error).message);
      return;
    } finally {
      setWaiting(false);
    }
  }

  if (info?.full_demo) return <TeacherWelcome onLogin={onLogin}/>;
  if (info?.public_demo) return <GuestWelcome onLogin={onLogin}/>;

  return <div className="access-layout">
    <section className="access-intro" aria-label="Sobre AXON">
      <a className="brand" href={publicAsset('')} aria-label="AXON"><img src={publicAsset('icon.svg')} alt=""/><span>AXON</span></a>
      <div className="access-story">
        <h1>Tu espacio educativo</h1>
        <p>Consulta tu agenda, prepara clases y estudia con un asistente conectado a tus materiales.</p>
        <ul className="access-roles" aria-label="Perfiles de AXON">
          <li><BookOpen size={22}/><div><strong>Alumnado</strong><span>Estudio, tutor y agenda personal.</span></div></li>
          <li><GraduationCap size={24}/><div><strong>Profesorado</strong><span>Clases, grupos y materiales.</span></div></li>
          <li><Settings2 size={22}/><div><strong>Administración</strong><span>Cuentas y organización del centro.</span></div></li>
        </ul>
      </div>
    </section>
    <main className="access-main">
      <div className="access-form">
        <h2>{invitation ? 'Activa tu invitación' : 'Accede a AXON'}</h2>
        {!info && !error && <Loading/>}
        {!info && error && <>
          <ErrorBox error={error}/>
          <button className="secondary" type="button" onClick={() => {setError(''); setReload(value => value + 1);}}>Reintentar conexión</button>
        </>}
        {info?.setup_required && <div className="access-recovery">
          <h3>Configura tu instalación</h3>
          <p>En el ordenador que ejecuta AXON, abre la carpeta del proyecto y ejecuta <code>./scripts/setup-admin.sh</code>. Después, recarga esta página e inicia sesión.</p>
        </div>}
        {info && !info.setup_required && <>
          <p>{invitation ? 'Elige una contraseña individual de al menos doce caracteres, con letras y números.' : 'Usa la cuenta que te ha facilitado tu centro.'}</p>
          <form onSubmit={submit} aria-busy={waiting}>
            {!invitation && <label className="field">
              <span>Usuario</span>
              <input autoComplete="username" autoCapitalize="none" spellCheck={false} maxLength={100} required value={username} onChange={event => setUsername(event.target.value)}/>
            </label>}
            <label className="field">
              <span>Contraseña</span>
              <div className="password-input">
                <input type={visible ? 'text' : 'password'} autoComplete={invitation ? 'new-password' : 'current-password'}
                  minLength={invitation ? 12 : 1} maxLength={128} required value={password} onChange={event => setPassword(event.target.value)}/>
                <button type="button" className="icon-button" aria-label={visible ? 'Ocultar contraseña' : 'Mostrar contraseña'}
                  aria-pressed={visible} onClick={() => setVisible(!visible)}>{visible ? <EyeOff size={18}/> : <Eye size={18}/>}</button>
              </div>
            </label>
            {invitation && <label className="field"><span>Repite la contraseña</span>
              <input type="password" autoComplete="new-password" minLength={12} maxLength={128}
                required value={confirmation} onChange={event => setConfirmation(event.target.value)}/>
            </label>}
            <ErrorBox error={error}/>
            {notice && <p className="access-notice" role="status">{notice}</p>}
            <button className="primary full" type="submit" disabled={waiting}>
              {waiting ? <><Loader2 className="spin" size={18}/>Comprobando…</>
                : <>{invitation ? 'Activar mi cuenta' : 'Iniciar sesión'}<ArrowRight size={17}/></>}
            </button>
          </form>
          {!invitation && !info.remote_demo && <details className="access-recovery">
            <summary>Recuperar acceso</summary>
            <p>Pide al administrador de tu instalación que restablezca tu contraseña. Si administras el servidor, puedes hacerlo desde su terminal con <code>PYTHONPATH=backend .venv/bin/python -m app.cli reset-access TU_USUARIO</code>.</p>
          </details>}
        </>}
        <div className="access-links">
          <InstallAxon/>
          <a className="text-button" href={publicAsset('kiosk.html')}>Información pública del centro</a>
        </div>
      </div>
    </main>
  </div>;
}
