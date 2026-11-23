# Clases de AXON

Abre **Clases** en el menú de aprendizaje. La aplicación funciona con las cuentas de AXON y sus datos se guardan en la instalación que estés usando. La conexión opcional de Google sigue en **Integraciones**.

## Crear una clase

1. Desde **Administración → Grupos y docencia**, prepara un curso, un grupo y una asignatura. Asigna esa materia y ese grupo al profesorado que deba crear la clase.
2. En **Clases**, pulsa **Nueva clase**. Indica nombre, descripción y color. El curso viene del grupo seleccionado.
3. En **Personas**, comparte el código de inscripción por un canal privado o invita a un alumno por su nombre de usuario. Los códigos se pueden renovar o cerrar. Las invitaciones duran siete días. El alumno las acepta dentro de AXON.
4. Añade profesorado responsable del mismo centro. Cada clase controla su propia matrícula. Una cuenta retirada necesita otra invitación. Un administrador gestiona las clases de su centro.

El alumnado ve su inscripción y el profesorado responsable. El profesorado ve la lista de su clase y puede crear equipos. El borrador, la entrega y la corrección de una actividad en equipo se comparten entre sus integrantes. Los equipos se crean con un conjunto fijo de alumnos para preservar el historial de su trabajo.

## Trabajar en una clase

- **Tablón** permite publicar y fijar avisos, habilitar comentarios y moderarlos.
- **Materiales** organiza archivos por tema. Admite PDF, TXT, MD, CSV, DOCX, XLSX, PPTX, PNG y JPEG. Los archivos de texto extraíble pueden aparecer como fuentes del asistente. Puedes guardar imágenes como adjuntos aunque el OCR local esté desactivado.
- **Actividades** admite tareas, ejercicios, cuestionarios, proyectos y exámenes. Guarda un borrador, añade instrucciones, preguntas, adjuntos, fecha de entrega y una rúbrica opcional. Pulsa **Publicar actividad** cuando esté lista. Los exámenes programados abren sus instrucciones y adjuntos a la hora prevista.
- El alumno puede escribir, adjuntar hasta cinco archivos activos, guardar un borrador y enviar una versión. El servidor comprueba el plazo. El equipo docente ve las versiones entregadas y devuelve una corrección con comentarios y puntuación opcional.
- **Calificaciones** muestra al alumnado su corrección individual o de equipo. Las notas las devuelve el personal autorizado desde la actividad. Las versiones de trabajo y las devoluciones se conservan en el historial.
- **Calendario** reúne eventos, sesiones, exámenes y entregas. Aparecen también en el calendario general para las personas inscritas y el personal autorizado. Las actividades aparecen en **Tareas**. Los avisos y recordatorios usan las preferencias de notificación de AXON.

Puedes archivar una clase para cerrar inscripciones y escrituras y conservar el acceso de lectura. Los documentos y entregas necesitan conexión a tu servidor, también cuando usas la PWA instalada.

## Usar el asistente de una clase

Pulsa **Preguntar a AXON** dentro de una clase. El asistente usa el modelo Ollama configurado, los recursos accesibles de esa clase y las fechas autorizadas. Puedes incluir tus propios recuerdos marcando la opción correspondiente. Las fuentes se enlazan al archivo que se consultó. El resumen de pendientes y la detección de solapamientos funcionan con los datos de AXON aunque Ollama esté apagado.

Para el equipo docente, el asistente ofrece borradores de actividades, cuestionarios, materiales, rúbricas, unidades y comentarios de corrección. Revisa las propuestas antes de guardarlas o publicarlas. Puedes pasar un borrador de actividad al formulario y editarlo. La devolución de notas requiere la acción explícita de una persona autorizada. En el chat general también puedes preguntar «¿Qué clases tengo?» y consultar materiales a los que tengas acceso.

La identidad del centro procede de BASE 100. Los materiales conservan su título y procedencia en el índice de documentos de AXON. Se consultan con los permisos de clase y van separados de las fuentes institucionales oficiales de BASE 200. BASE 300 enlaza clases y consulta los eventos y tareas vigentes.

## Instalación existente y demostración

Antes de actualizar, para AXON y crea una copia con `./scripts/backup.sh`. Ejecuta `./scripts/install.sh` para reconstruir la interfaz y aplicar la migración. La revisión 0007 añade tablas y relaciones de Clases y conserva las tablas anteriores, la información académica y la integración de Google. El historial de tareas, documentos y eventos previos sigue accesible en sus apartados.

Para probar los tres perfiles desde una base ficticia, usa `./scripts/init-demo.sh` en una carpeta de datos nueva. Incluye el escenario de Nébula, con etapas, grupos, tareas y guías ficticias. [Explorar el escenario](NEBULA.md) Abre la demostración siguiendo la guía de instalación y usa las credenciales privadas que el asistente genera para `alumno.demo`, `profesor.demo` y `admin.demo`. La administración de pruebas pertenece a esa base aislada. [Instalación y demostración](../INSTALL.md)

Para ejecutar las pruebas, usa `./scripts/test.sh`. La batería incluye roles, separación por clase, referencias cambiadas en rutas, adjuntos, plazos, historial, rúbricas y permisos de consulta del asistente.
