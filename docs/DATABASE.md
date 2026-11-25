# Datos y migraciones de AXON

## Referencia de la fase 0

La base SQLite de AXON utiliza WAL, claves externas, fechas UTC y un registro SQLAlchemy común. En la versión 0.7.0 las definiciones proceden de ocho archivos. [Registro de modelos](../backend/app/models.py) · [Configuración de SQLite](../backend/app/db.py) · [Inventario de las 82 tablas](auditoria/0.8/storage.tsv).

| Definiciones en `backend/app` | Tablas | Contenido representativo |
| --- | ---: | --- |
| `models.py` | 28 | Centros, cuentas, horarios, tareas históricas, conversaciones y documentos |
| `knowledge_models.py` | 15 | Alta de usuarios, perfiles, fuentes, criterios y estudio |
| `agent_models.py` | 11 | Ejecuciones del agente, vectores, automatizaciones y escenarios de notas |
| `atlas_models.py` | 5 | Núcleo institucional, políticas de proveedores e invitaciones remotas |
| `guest_models.py` y `teacher_models.py` | 2 + 1 | Sesiones públicas, cuotas y sesiones de demostración completa |
| `class_models.py` | 15 | Clases, participantes, equipos, publicaciones, entregas y evaluaciones |
| `nebula_models.py` | 5 | Tutorías, admisión, solicitudes, ponderaciones y guías de corrección |

En el TSV cada columna se describe por nombre, tipo SQLAlchemy y admisión de nulos. Las claves externas incluyen columna, destino y acción de borrado. Los índices, las restricciones adicionales y el SQL de FTS5 se consultan en las [ocho migraciones](../backend/migrations/versions). La revisión `0007` añade clases y la `0008` amplía la configuración educativa. En la auditoría se aplicó la cadena completa a una base vacía.

## Relaciones que debe preservar un cambio de propietario

- Una matrícula de grupo (`enrollments`), una asignación docente (`teacher_assignments`) y la pertenencia a una clase (`class_members`) tienen propósitos diferentes. Las lecturas por actor deben reproducir cada alcance.
- Las parejas `assignments/submissions` y `class_activities/class_submissions` siguen atendiendo tareas. Una entrega de clase puede tener revisiones, equipo, adjuntos y calificación. Conservar su origen e identidad al presentar una lista conjunta.
- `class_events` vincula una clase con el calendario compartido. Fechas de actividad, visibilidad de examen y eventos deben seguir concordando después de editar o cancelar.
- `documents` y `document_chunks` describen material cuyos bytes viven en `uploads`. La búsqueda FTS5 utiliza `search_index` y disparadores. La copia completa comprende base y archivos. La comprobación de restauración incluye búsquedas y descargas.
- El clon de demostración recorre las claves externas y remapea identificadores también dentro de JSON. Comprobar que ambos visitantes pueden abrir su material, que los identificadores y archivos difieren y que caducar una sesión preserva la otra. [Implementación del clon](../backend/app/demo_tenants.py).

## Protocolo propuesto para futuras migraciones

1. Ejecutar el comportamiento antiguo en una base ficticia vacía y en otra ya poblada. Preparar también un fixture histórico de la revisión afectada. Registrar versión, filas por identidad estable y resúmenes de los archivos.
2. Crear una copia con el mecanismo de AXON y restaurarla en otro directorio. Verificar `PRAGMA integrity_check`, `PRAGMA foreign_key_check`, cuentas y roles, archivos, búsquedas y aislamiento por centro.
3. Aplicar la revisión nueva a una segunda copia. Comparar claves, datos, relaciones y resultados observables. Distinguir en el informe las columnas nuevas que se esperan y cualquier diferencia pendiente.
4. Introducir primero cambios aditivos. Mantener un solo escritor para cada operación. Habilitar la lectura nueva tras comparar con la anterior. La creación de Nébula seguirá siendo explícita y comprobará el destino antes de sembrar.
5. Ensayar el retorno al código anterior sobre una copia compatible. Si ya hay escrituras que este no entiende, conservarlas, detener la activación y ensayar una corrección hacia delante. Una restauración de ensayo siempre se dirige a un destino nuevo.

Las pruebas existentes cubren instalación vacía, recuperación real de copias, búsqueda y una actualización desde `0002`. Cada revisión afectada necesitará su propio ensayo con datos representativos. [Pruebas de referencia](TESTING.md).
