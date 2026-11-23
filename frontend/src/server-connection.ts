export const CONNECTION_STORAGE_KEY = 'axon-server-url';
export const CONNECTION_TIMEOUT = 7000;
export const publicAsset = (file: string) => import.meta.env.BASE_URL + file;

export interface ServerInfo {
  service: 'axon';
  status: 'ok';
  version: string;
  auth: 'same-origin';
}

export function validateServerUrl(value: string): string {
  let url: URL;
  try {
    url = new URL(value.trim());
  } catch {
    throw new Error('Introduce una dirección HTTPS completa, como https://tu-servidor.example.');
  }
  const parts = url.hostname.split('.');
  const isDomain = parts.length >= 2 && url.hostname.length <= 253 &&
    /^[a-z]{2,63}$/i.test(parts[parts.length - 1]) &&
    parts.every(part => /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/i.test(part));
  if (url.protocol !== 'https:' || url.username || url.password || url.port ||
      url.pathname !== '/' || url.search || url.hash || !isDomain ||
      /(^|\.)(?:localhost|local|internal|lan|home|onion|test|invalid)$/i.test(url.hostname)) {
    throw new Error('Usa un dominio HTTPS público de AXON, sin puerto, rutas ni parámetros.');
  }
  return url.origin;
}

export async function checkServer(origin: string, signal?: AbortSignal): Promise<ServerInfo> {
  const url = validateServerUrl(origin);
  const timeout = new AbortController();
  const timer = setTimeout(() => timeout.abort(), CONNECTION_TIMEOUT);
  const cancel = () => timeout.abort();
  signal?.addEventListener('abort', cancel, {once: true});
  if (signal?.aborted) cancel();
  try {
    const response = await fetch(url + '/api/public/connection', {
      method: 'GET', credentials: 'omit', redirect: 'error', cache: 'no-store',
      referrerPolicy: 'no-referrer', signal: timeout.signal,
    });
    if (!response.ok) throw new Error('El servidor está desconectado o temporalmente inaccesible.');
    if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('La dirección no identifica un servidor AXON.');
    const data: unknown = await response.json();
    if (!data || typeof data !== 'object' ||
      !('service' in data) || data.service !== 'axon' ||
      !('status' in data) || data.status !== 'ok' ||
      !('auth' in data) || data.auth !== 'same-origin' ||
      !('version' in data) || typeof data.version !== 'string' ||
      !/^\d+\.\d+\.\d+(?:[-+][\w.-]{1,42})?$/.test(data.version)) {
      throw new Error('La dirección no identifica un servidor AXON compatible.');
    }
    return data as ServerInfo;
  } catch (error) {
    if (signal?.aborted) throw error;
    if (timeout.signal.aborted || !navigator.onLine) {
      throw new Error('El servidor no responde. Comprueba que AXON y el túnel estén encendidos.');
    }
    if (error instanceof TypeError) {
      throw new Error('AXON está desconectado o el servidor no ha autorizado esta dirección de GitHub Pages.');
    }
    throw error;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', cancel);
  }
}

export function savedServer(): string {
  try {
    const value = localStorage.getItem(CONNECTION_STORAGE_KEY);
    return value ? validateServerUrl(value) : '';
  } catch {
    return '';
  }
}
