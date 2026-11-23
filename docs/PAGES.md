# AXON en GitHub Pages y Cloudflare

La dirección de la edición independiente es [AXON](https://aimen-fe.github.io/AXON/). Desde la aplicación puedes consultar el estado y la versión de tu servidor, guardar su dirección y abrir el espacio educativo. La cuenta, las clases, los documentos y Ollama se usan desde el origen HTTPS de FastAPI.

GitHub Pages publica archivos estáticos. Su PWA abre el espacio de trabajo de AXON en una ventana del servidor para que la sesión y la API compartan origen. Las cookies de sesión de ese servidor siguen siendo `HttpOnly`, `Secure` en HTTPS y `SameSite=Strict`. Las operaciones autenticadas siguen validando el origen y el token CSRF. La PWA guarda únicamente el nombre HTTPS que hayas confirmado. El servidor solo autoriza que el origen configurado consulte `GET /api/public/connection`, que comunica el estado, la versión y el tipo de sesión. Esa consulta viaja sin cookies. El navegador hace la comprobación directamente y el backend conserva su política de acceso a documentos y otros datos.

## Instalar

Al proceder de una dirección anterior, instala AXON desde esta dirección y vuelve a introducir tu servidor HTTPS. Cada dirección de GitHub Pages tiene su propio alcance de PWA.

- **Android**. Abre la dirección permanente en Chrome y pulsa **Instalar AXON**. También puedes usar **Instalar aplicación** o **Añadir a pantalla de inicio** en su menú.
- **iPhone**. Abre la dirección permanente en Safari. Pulsa **Compartir → Añadir a pantalla de inicio**, activa **Abrir como app web** si aparece y pulsa **Añadir**.
- **Ordenador**. Abre la dirección permanente en Chrome o Edge y usa **Instalar AXON**. Safari en macOS permite usar **Archivo → Añadir al Dock**.

La PWA de GitHub Pages mantiene el mismo icono y dirección aunque se renueve un túnel. Cuando Fedora está apagado, muestra el estado desconectado. Tras una primera carga completa, el navegador conserva la interfaz pública para uso sin conexión. Las respuestas de la API y los documentos privados quedan fuera de la caché del Service Worker.

## Iniciar en Fedora

1. En la instalación local abre Ollama con `ollama serve` si el servicio aún está detenido. Comprueba el modelo con `ollama list`; si falta, ejecuta `ollama pull llama3.2:3b`. Ollama y FastAPI escuchan en las direcciones de loopback configuradas.
2. Arranca la edición local usando `./scripts/start.sh` y la dirección de tu instalación. Puedes usar AXON desde ahí sin publicar un túnel. El acceso desde otros dispositivos apunta a un origen HTTPS autorizado.
3. Para probar la PWA desde fuera con un enlace temporal, usa el [lanzador de la demostración aislada](../deploy/cloudflare/README.md). Antes de iniciar la demo, exporta `AXON_PAGES_ORIGIN=https://aimen-fe.github.io` en esa terminal. Si la demo ya estaba abierta, reiníciala para que reciba la configuración. El supervisor abre el túnel hacia su puerto de demostración y mantiene el puerto de Ollama fuera del túnel.
4. Copia la URL HTTPS que verifique el lanzador. En la PWA abre **Configuración → Conexión con servidor**, pégala y pulsa **Comprobar y guardar**. Cuando aparezca **Servidor conectado**, pulsa **Abrir AXON** para entrar en el espacio de trabajo que corresponda.
5. Si se apaga Fedora o se detiene Cloudflare, el espacio educativo quedará desconectado. Inicia Ollama y el servidor de nuevo. Si el enlace del túnel cambia, pega el nuevo en **Cambiar dirección**. La aplicación instalada conserva la dirección de GitHub Pages.

Un Quick Tunnel puede usarse gratuitamente en la demostración aislada, con una URL temporal. Para dar acceso sostenido a una instalación que maneja datos reales, usa un túnel gestionado con un dominio, un origen HTTPS fijo, protección de acceso y copias de seguridad. El host y el origen HTTPS deben configurarse explícitamente en el backend mediante `AXON_ALLOWED_HOSTS`, `AXON_ALLOWED_ORIGINS` y `AXON_COOKIE_SECURE=true`. El dominio o el alojamiento permanente pueden tener coste. [Documentación de Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)

## Compilar y publicar

El workflow de GitHub conserva el artefacto y el despliegue de Pages. Vite selecciona la entrada pública al compilar bajo `/AXON/`. Desde `frontend/` puedes reproducirlo con:

```bash
pnpm install --frozen-lockfile
pnpm exec tsc -b
pnpm exec vite build --base=/AXON/
```

La compilación valida el logotipo, el manifiesto, los iconos, los enlaces locales y los archivos necesarios para abrir la PWA. Se publica solamente `frontend/dist`. Para compilar el espacio de trabajo local con su formulario de acceso, ejecuta `pnpm run build`, con la base `/`.
