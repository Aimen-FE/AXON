# Centro Educativo Nébula

Nébula es una institución inventada para demostrar AXON. Su localidad es Villa Prisma, su país es «territorio ficticio» y su código es DEMO-001. Las personas, los materiales y la organización se han creado para el proyecto.

## Generar una demostración

Ejecuta `./scripts/init-demo.sh` en una instalación nueva o selecciona una carpeta de demostración nueva mediante `python -m app.cli init-demo CARPETA`. El asistente crea seis credenciales de acceso locales, distintas entre sí y guardadas en un archivo privado. Las cuentas `admin.demo`, `profesor.demo` y `alumno.demo` permiten recorrer los tres perfiles. Las demás identidades del centro tienen permisos y relaciones académicas pero carecen de una contraseña de acceso.

El escenario contiene 18 grupos y 108 clases. Incluye los cuatro cursos de ESO con grupos A y B, dos cursos de Bachillerato con modalidades de Ciencias y Tecnología y Humanidades y Ciencias Sociales, y dos cursos de cada uno de tres ciclos simulados de FP, de grado básico, medio y superior. Las asignaturas y los módulos son ejemplos configurables. Cada grupo tiene cuatro alumnos, un aula y un tutor.

Los horarios se generan con seis sesiones al día de lunes a viernes. Hay un recreo de 11:00 a 11:30. El generador asigna cada docente y aula a una sola sesión simultánea. Los contenidos, las denominaciones y los periodos de evaluación pertenecen a la simulación.

Cada clase tiene tres temas y sus apuntes originales, un tablón, tareas, ejercicios, cuestionarios, proyectos de equipo, exámenes anteriores corregidos y exámenes próximos. Hay respuestas enviadas, correcciones con rúbricas, adjuntos y actividades con el plazo vencido. Las fechas se generan respecto al momento de inicialización.

La carga completa se ejecuta una sola vez sobre la plantilla ficticia de instalación. Una segunda llamada reconoce su versión y conserva los registros existentes. Para empezar de nuevo, prepara otra carpeta de demostración. Las instalaciones de trabajo usan el asistente de configuración inicial y conservan sus propias cuentas.

## Recorrer el trabajo educativo

1. Entra como administrador, abre Administración y prepara un curso, grupo y asignatura de prueba. Crea una clase, añade un profesor y envía una invitación a un alumno.
2. Entra como profesor. Abre su clase, publica material y crea una actividad. Guarda y revisa el borrador antes de publicarlo.
3. Entra como alumno, acepta la invitación y abre la actividad. Guarda una respuesta, adjunta un archivo y entrega.
4. Vuelve al profesor para devolver comentarios y puntuación. El alumno podrá consultar su propia corrección y el historial.
5. Programa un examen y comprueba su aparición en el calendario del alumno.

Las guías internas de corrección requieren permisos docentes. Las ponderaciones de cada clase se configuran en Calificaciones. La devolución y modificación de notas conserva versiones y requiere una acción docente.

## Invitaciones y permisos

En Personas se ven las invitaciones pendientes y las solicitudes por código. Los códigos duran siete días, tienen un límite configurable de usos y pueden cerrarse o renovarse. La administración puede exigir revisión de solicitudes y habilitar o cerrar las invitaciones del profesorado. Las invitaciones individuales se consumen al aceptarlas y se pueden revocar antes.

Los códigos solo inscriben alumnos. El equipo docente administra sus propias clases. La administración tiene alcance sobre su centro. El servidor verifica estos límites en cada operación.

La demostración pública crea un centro ficticio separado para cada visitante. Puedes cambiar entre Alumno, Profesor y Administrador ficticio dentro de esa sesión. Los cambios se mantienen en el mismo centro de prueba para recorrer una actividad entre perfiles. La administración ficticia dispone de las funciones educativas de su centro y el acceso a las operaciones del servidor está cerrado por el perfil de demostración.

## Conocimiento y asistente

BASE 100 mantiene la identidad configurable de AXON. BASE 200 identifica los documentos originales de demostración y su procedencia. BASE 300 consulta clases, horarios, eventos, entregas y calificaciones según los permisos activos.

El asistente de clase puede explicar los tres temas con sus materiales autorizados. Las consultas de pendientes, próximas evaluaciones y entregas por corregir se resuelven con la base de datos. Las propuestas educativas generadas con Ollama se revisan antes de publicarse. La memoria y las conversaciones siguen perteneciendo al usuario de cada perfil.

## Retirada controlada de fuentes anteriores

El operador puede usar `python -m app.fictionalize --database BASE --manifest MANIFIESTO_PRIVADO --backup CARPETA_NUEVA`. El manifiesto privado contiene las cadenas que identifican los datos que se deban retirar. El comando conserva las cuentas, prepara una copia de base y archivos, restaura esa copia en otra carpeta y verifica la integridad antes de modificar datos.

La retirada sustituye la identidad afectada, retira sus documentos y contactos académicos importados y limpia las referencias señaladas en textos, índices y metadatos. Los originales quedan en la copia privada. El manifiesto, las bases y las copias deben permanecer fuera de la publicación. Ejecuta el procedimiento con la instancia detenida.
