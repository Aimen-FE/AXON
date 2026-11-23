# Demostraciones HTTPS en Cloudflare

## Aplicación completa de demostración

El Quick Tunnel conecta con una instancia ficticia independiente, en loopback 8016 por defecto. Si otra instalación usa ese puerto, selecciona uno libre con `AXON_TEACHER_PORT` antes de abrir la demo. Cada visitante con el enlace recibe una sesión temporal y un centro Nébula separado. Puede cambiar entre Alumno, Profesor y Administrador ficticio para recorrer la creación, entrega y corrección de una actividad en su propio centro. Las operaciones de administración del servidor permanecen cerradas. Instala Ollama con `llama3.2:3b` y prepara el conector siguiendo las instrucciones del script:

```bash
.venv/bin/python scripts/setup-cloudflared.py --download-public-connector
./AXON --no-window --no-browser
./AXON --status
./AXON --stop-demo
```

El supervisor conserva los procesos y verifica HTTPS. Cloudflare puede cambiar el nombre al recrear el túnel. Si instalaste AXON desde GitHub Pages, actualiza el enlace en Conexión con servidor. La PWA conserva su dirección original. [Configurar la PWA de GitHub Pages](../../docs/PAGES.md) Consulta [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).

## Modalidad con Access

Si tienes un dominio y una aplicación de Access autorizados, puedes preparar una demostración con usuarios invitados. Configura el conector hacia `127.0.0.1:8015` y protege el dominio con una política por correos autorizados. Usa otra carpeta y evita ejecutar simultáneamente la demo restringida anterior, que reserva el mismo puerto.

1. Ejecuta `PYTHONPATH=backend .venv/bin/python -m app.remote_operator prepare --destination data/atlas-demo`.
2. Copia `remote.env.example` a `data/atlas-demo/remote.env`. Indica tus nombres y audiencia de Access. Guarda el archivo local con permisos 600.
3. Emite la invitación inicial con `PYTHONPATH=backend .venv/bin/python -m app.remote_operator invite --destination data/atlas-demo --username atlas.owner --email CORREO_AUTORIZADO`. El token se guarda en un archivo local de permisos 600. Úsalo como fragmento del dominio autorizado y entrégalo por un canal privado.
4. Comprueba la configuración con `PYTHONPATH=backend .venv/bin/python -m app.remote_operator check --config data/atlas-demo/remote.env` y arranca con el mismo comando sustituyendo `check` por `serve`.

Las cuentas de esta modalidad se activan tras aceptar la invitación individual. AXON valida firma, emisor, audiencia e identidad de Access en el servidor. Consulta [la documentación de Cloudflare Access](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/).
