# AXON

AXON es una plataforma educativa independiente y configurable. La demostración usa el Centro Educativo Nébula, situado en Villa Prisma, un territorio ficticio. Sus personas, documentos y actividades se han creado para el proyecto.

AXON reúne el asistente, la agenda y los materiales de un centro educativo en una web que se puede instalar como aplicación. El servidor guarda los datos en SQLite y puede conversar con un modelo de Ollama en el mismo equipo.

- **Alumnado** · Chat, memoria personal, calendario, horarios, exámenes, tareas, documentos permitidos y tutor.
- **Profesorado** · Asignaturas y grupos asignados, materiales, propuestas de exámenes y tareas, calendarios y comunicados.
- **Administración** · Cuentas y roles, grupos, asignaciones, núcleo de conocimiento, modelos, integraciones, auditoría y copias.
- **Conocimiento** · BASE 100 identifica la instalación, BASE 200 conserva fuentes con su procedencia y BASE 300 consulta los registros vigentes según los permisos.

## Instalar y abrir

En Linux, instala Python 3.12, Node.js 22.13 o posterior de la rama 22, o Node.js 24, y pnpm 11. Para instalar la edición, clona el repositorio y ejecuta el asistente desde su carpeta.

```bash
git clone https://github.com/Aimen-FE/AXON.git
cd AXON
./scripts/install.sh
./scripts/setup-admin.sh
./scripts/start.sh
```

Abre [AXON en este ordenador](http://127.0.0.1:8000). El asistente de terminal crea el centro y su primer administrador con la contraseña que escribas. Crea las demás cuentas desde **Administración → Cuentas**. Asigna un grupo y una asignatura a cada profesor en **Grupos y docencia**. Consulta la [guía de instalación](INSTALL.md) para configurar HTTPS, preparar una demostración ficticia o restablecer el acceso.

## Entorno ficticio completo

La demostración incluye ESO, Bachillerato y FP, con 18 grupos, 108 clases, horarios, materiales, entregas y evaluaciones relacionadas. [Guía de Nébula](docs/NEBULA.md)

## Clases

Crea aulas con el profesorado y el alumnado de AXON. Cada clase combina tablón, actividades, materiales, personas, calificaciones y calendario. El asistente puede consultar materiales autorizados y preparar borradores para revisión. [Manual de Clases](docs/CLASES.md)

## Instalar la aplicación web

La PWA pública tiene dirección estable en GitHub Pages y abre el espacio autenticado en tu servidor HTTPS. [Conectar e instalar la PWA](docs/PAGES.md)

En la portada o en la barra superior, pulsa **Instalar AXON**. En Chrome o Edge aparecerá la opción de instalar si el navegador la ofrece. En iPhone y iPad, abre AXON con Safari, toca **Compartir → Añadir a pantalla de inicio** y activa **Abrir como app web** si aparece. La instalación conserva el origen y la sesión de ese navegador. Para compartirla con un móvil, abre la dirección HTTPS de tu instalación.

Sin conexión se muestra una página informativa. Desde Configuración puedes guardar durante siete días una copia de la información que el centro ya ha hecho pública. Chat, Ollama y operaciones sobre tus datos requieren conexión con el servidor.

## Conectar Ollama

Arranca Ollama y prepara el modelo:

```bash
ollama pull llama3.2:3b
ollama list
```

Copia `.env.example` a `.env` para elegir otro nombre en `AXON_OLLAMA_MODEL` o ajustar el modo. **Modelos y recursos** comprueba su disponibilidad. El calendario y varias herramientas estructuradas funcionan sin inferencia. OCR, dictado, memoria semántica y servicios externos requieren componentes opcionales que describe [INSTALL.md](INSTALL.md).

## Desarrollar y colaborar

Ejecuta `./scripts/test.sh` para la batería y el build. Usa `./scripts/start-backend.sh --reload` y `./scripts/start-frontend.sh` en dos terminales para desarrollar con recarga. Consulta [cómo contribuir](CONTRIBUTING.md), [la arquitectura](ARCHITECTURE.md), [seguridad](SECURITY.md) y [la guía de pruebas de la PWA](docs/VERIFICACION.md).

## Licencia

El código propio de AXON se distribuye bajo [MIT](LICENSE). Los componentes de terceros conservan sus propias licencias y atribuciones. [Licencias y avisos](docs/LICENCIAS.md).
