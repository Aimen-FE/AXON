import {useEffect, useRef, useState, type FormEvent} from 'react';
import {ArrowUpRight, Cable, CircleCheck, CloudOff, RefreshCw, Settings2} from 'lucide-react';
import {InstallAxon} from './pwa';
import {checkServer, CONNECTION_STORAGE_KEY, publicAsset, savedServer, validateServerUrl, type ServerInfo} from './server-connection';
import './server-portal.css';

type Connection = {origin: string; info?: ServerInfo; error?: string; checking?: boolean};

export default function ServerPortal() {
  const [origin, setOrigin] = useState(savedServer);
  const [address, setAddress] = useState(origin);
  const [connection, setConnection] = useState<Connection>({origin});
  const [formError, setFormError] = useState('');
  const [editing, setEditing] = useState(!origin);
  const pending = useRef<AbortController | null>(null);
  const panel = useRef<HTMLElement | null>(null);

  function startCheck(target: string, save: boolean) {
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    setConnection(previous => previous.origin === target
      ? {...previous, error: undefined, checking: true}
      : {origin: target, checking: true});
    void checkServer(target, controller.signal).then(info => {
      if (controller.signal.aborted) return;
      setConnection({origin: target, info});
      if (save) {
        localStorage.setItem(CONNECTION_STORAGE_KEY, target);
        setOrigin(target);
        setAddress(target);
        setEditing(false);
      }
    }).catch((error: Error) => {
      if (!controller.signal.aborted) setConnection({origin: target, error: error.message});
    });
  }

  useEffect(() => {
    if (!origin) return;
    const refresh = () => {
      if (!document.hidden && !editing) startCheck(origin, false);
    };
    const disconnected = () => {
      pending.current?.abort();
      setConnection({origin, error: 'El dispositivo está sin conexión. AXON volverá a comprobar el servidor al recuperar Internet.'});
    };
    if (!editing) refresh();
    const timer = window.setInterval(refresh, 20000);
    window.addEventListener('online', refresh);
    window.addEventListener('offline', disconnected);
    document.addEventListener('visibilitychange', refresh);
    return () => {
      pending.current?.abort();
      clearInterval(timer);
      window.removeEventListener('online', refresh);
      window.removeEventListener('offline', disconnected);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, [origin, editing]);

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      const target = validateServerUrl(address);
      setFormError('');
      startCheck(target, true);
    } catch (error) {
      setFormError((error as Error).message);
    }
  }

  function disconnect() {
    pending.current?.abort();
    localStorage.removeItem(CONNECTION_STORAGE_KEY);
    setOrigin('');
    setAddress('');
    setConnection({origin: ''});
    setFormError('');
    setEditing(true);
    panel.current?.focus();
  }

  const online = connection.origin === origin && !!origin && !!connection.info;
  return <main className="server-portal">
    <header className="server-top">
      <a className="server-logo" href={publicAsset('')} aria-label="AXON">
        <img src={publicAsset('icon.svg')} alt="" width={38} height={38}/>
        <span>AXON<span className="server-logo-dot">.</span></span>
      </a>
      <InstallAxon/>
    </header>
    <div className="server-content">
      <section className="server-heading">
        <h1>Tu espacio educativo</h1>
        <p>Conecta con AXON para usar el asistente, consultar tus clases y trabajar con tus materiales.</p>
        {online
          ? <a className="primary server-open" href={origin + '/'} target="_blank" rel="noopener noreferrer">
              Abrir AXON <ArrowUpRight size={18}/>
            </a>
          : <button className="secondary" type="button" onClick={() => {
              setEditing(true); panel.current?.focus();
            }}><Settings2 size={17}/> Configuración</button>}
      </section>
      <section className="server-card" ref={panel} tabIndex={-1} aria-labelledby="server-card-title">
        <div className="server-card-heading">
          <Cable size={20}/>
          <h2 id="server-card-title">Conexión con servidor</h2>
        </div>
        <div className={'server-status ' + (online ? 'connected' : '')} role="status">
          {online ? <CircleCheck size={18}/> : <CloudOff size={18}/>}
          <strong>{online ? 'Servidor conectado' : connection.checking ? 'Comprobando conexión…'
            : origin || connection.error ? 'Servidor desconectado' : 'Configura tu servidor'}</strong>
          {online && <span>Versión {connection.info?.version}</span>}
        </div>
        {!!origin && <p className="server-origin">{origin}</p>}
        {!!connection.error && <p className="server-error" role="alert">{connection.error}</p>}
        {editing ? <form onSubmit={save}>
          <label htmlFor="server-url">Dirección HTTPS de AXON</label>
          <input id="server-url" type="url" required value={address} inputMode="url" autoComplete="url"
            autoCapitalize="none" spellCheck={false} maxLength={270} placeholder="https://tu-servidor.example"
            onChange={event => {setAddress(event.target.value); setFormError('')}}/>
          {formError && <p className="server-error" role="alert">{formError}</p>}
          <div className="button-row">
            <button className="primary" disabled={connection.checking}>Comprobar y guardar</button>
            {origin && <button className="secondary" type="button" onClick={() => {
              setAddress(origin); setFormError(''); setEditing(false);
            }}>Cancelar</button>}
          </div>
        </form> : <div className="button-row">
          <button className="secondary" type="button" onClick={() => setEditing(true)}>Cambiar dirección</button>
          <button className="secondary" type="button" disabled={connection.checking}
            onClick={() => startCheck(origin, false)}><RefreshCw size={15}/> Comprobar</button>
          <button className="text-button" type="button" onClick={disconnect}>Desconectar</button>
        </div>}
        <p className="server-note">Abre AXON para iniciar sesión en tu servidor. Esta aplicación guarda únicamente su dirección.</p>
      </section>
    </div>
  </main>;
}
