import {useState, useSyncExternalStore} from 'react';
import {Download, X} from 'lucide-react';
import {Modal} from './core';

interface InstallPrompt extends Event {
  prompt: () => Promise<unknown>;
  userChoice: Promise<{outcome: 'accepted' | 'dismissed'}>;
}

const launchMode = matchMedia('(display-mode: standalone)');
const isInstalled = () => launchMode.matches || !!(navigator as Navigator & {standalone?: boolean}).standalone;
let state = {prompt: null as InstallPrompt | null, installed: isInstalled()};
const listeners = new Set<() => void>();

function update(next: typeof state) {
  state = next;
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

window.addEventListener('beforeinstallprompt', event => {
  event.preventDefault();
  update({...state, prompt: event as InstallPrompt});
});
window.addEventListener('appinstalled', () => update({installed: true, prompt: null}));
launchMode.addEventListener('change', () => update({...state, installed: isInstalled()}));

export function InstallAxon({compact = false}: {compact?: boolean}) {
  const {prompt, installed} = useSyncExternalStore(subscribe, () => state);
  const [manual, setManual] = useState(false);
  const [installing, setInstalling] = useState(false);
  const ios = /iPhone|iPad|iPod/.test(navigator.userAgent)
    || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);

  async function install() {
    if (!prompt) {
      setManual(true);
      return;
    }
    setInstalling(true);
    try {
      await prompt.prompt();
      const choice = await prompt.userChoice;
      if (state.prompt === prompt) {
        update({prompt: null, installed: state.installed || choice.outcome === 'accepted'});
      }
    } catch {
      if (state.prompt === prompt) update({...state, prompt: null});
      setManual(true);
    } finally {
      setInstalling(false);
    }
  }

  if (installed) return null;
  return <>
    <button
      type="button"
      className={compact ? 'icon-button install-icon' : 'secondary install-axon'}
      aria-label="Instalar AXON"
      title="Instalar AXON"
      aria-busy={installing}
      disabled={installing}
      onClick={() => void install()}
    >
      <Download size={17}/>
      {!compact && (installing ? 'Abriendo instalación…' : 'Instalar AXON')}
    </button>
    {manual && <Modal title="Instalar AXON" onClose={() => setManual(false)}>
      <div className="install-help">
        {!window.isSecureContext
          ? <p>Abre AXON con la dirección HTTPS de tu centro. Si estás en el ordenador que ejecuta el servidor, utiliza localhost.</p>
          : ios
            ? <ol>
              <li>Abre esta dirección en <strong>Safari</strong>.</li>
              <li>Toca <strong>Compartir</strong> y elige <strong>Añadir a pantalla de inicio</strong>.</li>
              <li>Activa <strong>Abrir como app web</strong> si aparece y toca <strong>Añadir</strong>.</li>
            </ol>
            : <>
              <p>Abre el menú de tu navegador y busca <strong>Instalar AXON</strong> o <strong>Añadir a pantalla de inicio</strong>. En Safari para Mac, utiliza <strong>Archivo → Añadir al Dock</strong>.</p>
              <p>Si no aparece la opción, prueba con Chrome, Edge o Safari en un dispositivo compatible.</p>
            </>}
        <p className="fine-print">La app abre en su propia ventana. El chat y Ollama requieren conexión con el servidor de tu instalación.</p>
        <button type="button" className="secondary" onClick={() => setManual(false)}><X size={16}/>Cerrar</button>
      </div>
    </Modal>}
  </>;
}
