# AXON 0.8 · Auditoría de la versión de referencia

**Fase 0, 25 de noviembre de 2026.** La referencia es la versión 0.7.0 de AXON en el commit [80fef73](https://github.com/Aimen-FE/AXON/commit/80fef73e734768593292a2dd20eda89755ebeaba). Se exportaron los archivos de ese commit a un directorio temporal. Las pruebas de instalación y demostración utilizaron bases ficticias independientes. Los resultados permiten comparar cada reemplazo con un comportamiento conocido.

El [mapa de módulos](modulos.md) relaciona las capacidades actuales con sus responsables futuros. El [plan de migración](../../../ROADMAP.md) fija el orden, los criterios de aceptación y la vuelta atrás.

## Qué hay hoy

| Superficie | Medición en la referencia | Qué permite comprobar |
| --- | --- | --- |
| API local | 35 routers registrados, 167 rutas diferentes y 202 combinaciones de método y ruta. 86 GET, 77 POST, 14 PUT, 13 PATCH y 12 DELETE | El [inventario HTTP](http.tsv) recoge parámetros, cuerpo de entrada y respuestas de éxito declaradas. La política de acceso depende también del perfil de ejecución. |
| Persistencia | 82 tablas registradas por SQLAlchemy, 165 claves externas y ocho revisiones Alembic hasta `0008` | El [inventario de almacenamiento](storage.tsv) identifica columnas, claves y módulo de origen. El índice FTS5 y sus disparadores se crean mediante migración. |
| Código del servidor | 82 archivos Python en `backend/app`. El [grafo de importaciones](imports.tsv) contiene 358 dependencias internas directas de primer nivel y 480 al incluir las anidadas | Cada arista cuenta un par distinto de módulos. El análisis estático incluye las importaciones dentro de funciones. La carga dinámica y las relaciones en SQL o JSON quedan fuera de esta medida. |
| Interfaz | React y TypeScript comparten componentes y estilos. Vite construye una aplicación en `/` y un portal independiente en `/AXON/` | La sesión se abre en el origen del servidor. El portal estático descubre el servidor por HTTPS. El manifiesto y la caché se resuelven respecto a su propio alcance. |
| Referencia educativa | El generador Nébula reproduce 18 grupos, 108 clases y 540 sesiones de horario. Incluye ESO, Bachillerato y FP básica, media y superior | La prueba comprueba el mismo recuento al repetir la población, cuatro alumnos y un docente por clase, ausencia de solapamientos y al menos 100 calificaciones. |
| Pruebas | 209 casos en 28 archivos de pytest. La ejecución completa con modelos locales superó los 209. TypeScript y las dos compilaciones pasaron | Chrome reabrió el portal local de Pages sin red. Se documentan requisitos, intentos y límites en [Pruebas de referencia](../../TESTING.md). |

## Problemas que condicionan la migración

| Prioridad | Hallazgo reproducible | Consecuencia y decisión propuesta |
| --- | --- | --- |
| Alta | Las 202 operaciones declaran un esquema JSON de éxito vacío en OpenAPI. Hay 86 esquemas de componentes, incluidos modelos de entrada. En ejecución también aparecen descargas y redirecciones. | La ruta y los parámetros pueden seguir iguales mientras React recibe otro formato. Capturar ejemplos de respuestas, códigos, cabeceras y archivos por rol antes de introducir tipos de salida. |
| Alta | `auth.current_user` resuelve sesión y CSRF, comprueba perfiles de demo, cuotas por ruta y módulos habilitados. `policy` y `class_policy` aplican además reglas distintas de grupo y clase. | Repartir estas decisiones sin fijar el orden podría ampliar el acceso. Caracterizar una misma acción como visitante, miembro, docente ajeno y administrador de otro centro. Conservar las restricciones al llamar desde el asistente. |
| Alta | `education.assignments_for` combina las tareas históricas con `classwork.class_assignments`. `classwork` usa las notificaciones de `education`. Los archivos, las calificaciones y los calendarios enlazan registros de varios módulos. | Unificar únicamente la lectura al principio. Identificar la procedencia de cada fila, conservar las dos vías de escritura y probar con ambas clases de entrega. |
| Alta | Alembic carga el registro compartido a través de `models.py`. `demo_tenants.rows_for` recorre sus claves externas y `clone` reasigna identificadores en JSON y copia archivos. | Una tabla que dejara de registrarse podría faltar en las copias por visitante aunque el servidor arrancara. Verificar inventario, referencias, archivos y aislamiento con dos demostraciones simultáneas. |
| Alta | `classwork` sincroniza eventos al publicar actividades y avisa a los miembros. El índice de búsqueda se mantiene también con disparadores de SQLite. | Una extracción que confirme sus cambios por separado puede dejar eventos huérfanos, avisos dobles o búsquedas obsoletas. Mantener una transacción por operación y probar el fallo intermedio y el reintento. |
| Media | Las importaciones de primer nivel forman un grafo sin ciclos. Al incluir las anidadas aparecen dos conjuntos mutuamente alcanzables, de 29 y 4 módulos. Ejemplos directos son `classes ↔ education_settings` y `memory ↔ semantic`. `tools` alcanza directamente 26 módulos e invoca el manejador HTTP `classes.list_classes`. | Hoy el arranque funciona. Para poder cambiar un lado sin arrastrar el otro, extraer casos de uso invocables desde HTTP y herramientas, y un único responsable de la invalidación del índice. |
| Media | `main.create_app` depende de 41 módulos internos y reúne migraciones, mantenimiento, filtros de seguridad, registro de rutas y servicio de archivos. En React, `App.tsx` coordina sesión, navegación y roles, y `classes.tsx` mezcla varios flujos en 559 líneas. | Desacoplar por tarea observable. Un primer corte comprobable es mantener la navegación y sustituir la consulta del listado de clases. Revisar el tamaño después de definir el límite funcional. |
| Media | En una exportación limpia, dos pruebas reciben 404 en `/` si falta la compilación local. `scripts/test.sh` llama primero a pytest. La única acción de GitHub compila y publica Pages desde `main` o bajo petición. | Compilar la aplicación antes de probar el servidor. En fase 1 hacer obligatorios en cada PR el tipado, las dos compilaciones y la batería básica, con publicación reservada a su flujo actual. |

## Dependencias de ejecución

FastAPI, Pydantic y Uvicorn forman la interfaz HTTP. SQLAlchemy y Alembic gestionan SQLite con claves externas y búsqueda FTS5. El navegador utiliza React, Vite, Tailwind y Lucide. Los archivos de versiones fijadas son [requirements.lock](../../../backend/requirements.lock) y [pnpm-lock.yaml](../../../frontend/pnpm-lock.yaml).

Ollama funciona como proceso local. La búsqueda semántica utiliza FastEmbed/ONNX. La lectura de documentos usa extractores de PDF y Office, y puede requerir Tesseract. Voz y dictado usan eSpeak NG y Vosk. El cálculo simbólico utiliza SymPy. Se mantienen los límites de los procesos de trabajo. Classroom, búsqueda web, proveedores externos optativos y Cloudflare tienen adaptadores y requisitos de red distintos. El paso de CI debe poder repetirse con sustitutos controlados y datos ficticios.

## Cómo volver a obtener los inventarios

Desde la raíz de la rama de auditoría, usar un intérprete con las dependencias de AXON. Un directorio exportado con `git archive 80fef73` permite regenerarlos incluso después de que evolucione la rama. El programa inspecciona el código indicado por `PYTHONPATH`, un directorio vacío y una base en memoria. Su salida contiene definiciones de código.

```bash
audit_dir="$PWD/docs/auditoria/0.8"
reference_dir=$(mktemp -d)
git archive 80fef73 | tar -x -C "$reference_dir"
for kind in http storage imports; do
  PYTHONPATH="$reference_dir/backend" python "$audit_dir/snapshot.py" "$kind" > "$reference_dir/$kind.tsv"
  diff -u "$audit_dir/$kind.tsv" "$reference_dir/$kind.tsv" || exit 1
done
```

Los siguientes documentos detallan los contratos que un listado de rutas no expresa por sí solo. [Datos y migraciones](../../DATABASE.md) · [Permisos y perfiles](../../SECURITY.md) · [Pruebas y cobertura](../../TESTING.md).
