import React from 'react';
import ReactDOM from 'react-dom/client';
import ServerPortal from './server-portal';
import {publicAsset} from './server-connection';
import './style.css';
import './agent.css';
import './edition.css';

ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><ServerPortal/></React.StrictMode>);
if ('serviceWorker' in navigator && import.meta.env.PROD) {
  navigator.serviceWorker.register(publicAsset('sw.js') + '?static=1').catch(() => {});
}
