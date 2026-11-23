# Instalar AXON

AXON sirve una única web mediante FastAPI, con el frontend compilado en la misma dirección. La instalación de referencia utiliza Linux, Python 3.12, Node.js 24 y pnpm 11. El script también acepta Python 3.13 y Node.js 22.13+. En distribuciones que usen otra versión por defecto, asigna `AXON_PYTHON` a tu ejecutable de Python 3.12/3.13. Para otras plataformas, usa un entorno Linux (por ejemplo WSL2) para seguir este procedimiento. Instalar las dependencias por primera vez necesita acceso a PyPI y al registro de npm.

```bash
./scripts/install.sh
./scripts/setup-admin.sh
./scripts/start.sh
```

1. El instalador crea `.venv`, aplica las versiones fijadas, construye la interfaz y migra una base vacía. Puedes repetir esta operación para actualizar una instalación.
2. El asistente pide centro, nombre de usuario, nombre visible y dos entradas ocultas de la contraseña. Crea un único administrador si la base está vacía. Utiliza una contraseña individual de al menos 12 caracteres.
3. Abre [http://127.0.0.1:8000](http://127.0.0.1:8000) y entra con esa cuenta. Desde Administración puedes crear un curso académico, cursos, grupos, asignaturas, aulas y cuentas. Matricula al alumnado y asigna a cada profesor sus grupos y materias. Un administrador puede cambiar el rol de otra cuenta. AXON solicita otro inicio de sesión al cambiar los permisos.
4. Para detener la ejecución en la terminal, pulsa Ctrl+C. Para usar un icono de Linux, consulta [el lanzador](deploy/desktop/README.md).

## Crear y recuperar cuentas

1. Entra con una cuenta de administración y abre **Administración → Cuentas → Crear cuenta**.
2. Escribe un identificador único, como `alumno.ejemplo`, y un nombre visible en **Nombre ficticio**. El identificador se usa al iniciar sesión y admite minúsculas sin tildes, números y `.`, `_`, `@` o `-`.
3. Selecciona **Alumno** para crear una cuenta de prueba con permisos limitados. Elige **Profesor** si necesita gestionar sus grupos y asignaturas. Puedes asignar los grupos de matrícula del alumnado al crear la cuenta.
4. Introduce una contraseña inicial individual de al menos 12 caracteres y pulsa **Crear cuenta**. La persona puede cambiarla en **Mi perfil** después de entrar.

AXON guarda las cuentas en la base de datos de cada instalación y protege las contraseñas mediante un hash. Mantén la base y las credenciales fuera del repositorio.

Para recuperar una cuenta activa, un operador con acceso al servidor ejecuta desde la raíz del proyecto:

```bash
PYTHONPATH=backend .venv/bin/python -m app.cli reset-access TU_USUARIO
```

El terminal pide la nueva contraseña y AXON invalida las sesiones anteriores. El alta de perfiles académicos privados y su enlace de un solo uso siguen disponibles mediante el [procedimiento del operador](docs/OPERACION.md).

## Demostración local con cuentas ficticias

```bash
./scripts/init-demo.sh
AXON_DATA_DIR=data/local-demo AXON_DEMO=true ./scripts/start.sh
```

Detén primero cualquier AXON que use el mismo puerto. Las seis cuentas ficticias, sus claves distintas y el escenario completo de Nébula con 108 clases se crean una sola vez. El fichero `data/local-demo/demo-credentials.txt` se guarda con permisos 600. Léelo localmente, utiliza las cuentas para probar los roles y custodia las credenciales como cualquier contraseña. Los datos de esta demo se guardan en otra carpeta. Consulta [las modalidades de Cloudflare](deploy/cloudflare/README.md) para compartir una demo aislada.

## Configuración y Ollama

Copia `.env.example` a `.env` si necesitas persistir opciones. Mantén ese archivo local y protegido. El entorno del proceso tiene prioridad. Por defecto, los datos van a `data/`, se sirve por loopback y no se inicia una demo.

```bash
ollama serve                 # omite este paso si ya hay un servicio iniciado
ollama pull llama3.2:3b       # en otra terminal si Ollama está en primer plano
ollama list
```

Establece `AXON_AI_MODE=ollama` para requerir inferencia real, o `auto` para disponer de herramientas y un modo de respuesta identificado cuando el modelo no esté disponible. Verifica el modelo desde **Modelos y recursos**. Ollama debe escuchar en loopback. La aplicación comparte una cola y aplica límites de tiempo.

Componentes opcionales:

| Función | Preparación |
| --- | --- |
| Semántica | `PYTHONPATH=backend .venv/bin/python -m app.cli setup-semantic --download-public-model`. Descarga explícita del modelo público. La búsqueda por texto sigue disponible. |
| OCR y dictado | `PYTHONPATH=backend .venv/bin/python -m app.cli setup-media --download-public-models`. OCR requiere Tesseract y libseccomp, dictado requiere Vosk, su modelo y libseccomp. El navegador pide permiso de micrófono bajo HTTPS o localhost. |
| Lectura en voz alta | Instala `espeak-ng` en el equipo servidor. |
| Classroom | OAuth de Google configurado por el operador. Modo de prueba disponible sin credenciales externas. |
| Investigación y proveedores opcionales | Lectura de URLs públicas con consentimiento. El buscador y las consultas puntuales a Gemini/Groq dependen de tu configuración. El chat habitual utiliza Ollama. |

## Acceso HTTPS y PWA

Para acceder desde otro dispositivo, configura un proxy HTTPS administrado y conserva AXON ligado a `127.0.0.1:8000`. Pasa el encabezado Host original desde el proxy. Redirige HTTP a HTTPS. Con un dominio propio, la configuración de ejemplo es:

```dotenv
AXON_ALLOWED_HOSTS=axon.example.org
AXON_ALLOWED_ORIGINS=https://axon.example.org
AXON_COOKIE_SECURE=true
```

Cambia el dominio por el tuyo. Mantén Ollama, la base, las copias y los documentos fuera del directorio servido. Antes de usar datos de terceros, revisa los requisitos de tu centro, las copias y los controles del proxy. El contexto local `http://127.0.0.1:8000` también permite probar el trabajador de la PWA.

Si instalas la PWA desde GitHub Pages, configura la dirección HTTPS del espacio de trabajo desde el portal estable. [Conexión mediante GitHub Pages](docs/PAGES.md)

Si instalas directamente desde el servidor, su dirección HTTPS es el origen de la aplicación instalada. Si utilizas un Quick Tunnel y cambia su dirección, instala nuevamente la PWA desde el enlace nuevo. La instalación de la PWA añade el icono y la ventana de AXON, mientras el servidor sigue ejecutándose en tu entorno.
