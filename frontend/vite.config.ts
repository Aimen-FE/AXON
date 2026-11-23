import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import {checkPagesBuild} from './scripts/check-pages-build.mjs';

export default defineConfig(({mode}) => {
  const pagesBase = '/AXON/';
  let isPortal = false;
  return {
    base: mode === 'pages' ? pagesBase : '/',
    plugins: [react(), tailwindcss(), {
      name: 'axon-pages',
      configResolved(config) {
        isPortal = config.base === pagesBase;
      },
      transformIndexHtml: {
        order: 'pre',
        handler(html) {
          if (!isPortal) return;
          return {
            html: html.replace('/src/main.tsx', '/src/pages-main.tsx'),
            tags: [{
              tag: 'meta',
              attrs: {
                'http-equiv': 'Content-Security-Policy',
                content: "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self' https:; object-src 'none'; base-uri 'self'; form-action 'none'",
              },
              injectTo: 'head-prepend',
            }],
          };
        },
      },
    }, checkPagesBuild(pagesBase)],
    server: {host: '127.0.0.1', proxy: {'/api': {target: 'http://127.0.0.1:8000', changeOrigin: false}}},
    build: {sourcemap: false},
  };
});
