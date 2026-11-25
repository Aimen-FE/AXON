# Permisos y perfiles de AXON

Este documento fija los comportamientos de seguridad a comparar durante la reconstrucción. El procedimiento para comunicar problemas de seguridad está en [la política del repositorio](../SECURITY.md).

| Actor o entrada | Condición observable en 0.7 | Referencias en `backend/tests` |
| --- | --- | --- |
| Instalación nueva y operador local | Primera cuenta creada de forma explícita, incluso si llegan dos solicitudes simultáneas. La recuperación o el cambio de privilegios invalida las sesiones afectadas. | `test_installation.py`, `test_security.py` |
| Alumno | Acceso a clases en las que participa, recursos compartidos y entregas propias o de su equipo. El instante de apertura gobierna los adjuntos del examen. El solucionario es de acceso docente. | `test_classes.py`, `test_nebula.py` |
| Profesor | Permisos según centro, docencia y pertenencia a la clase. Cambios académicos propuestos por el asistente requieren confirmación y una nueva comprobación de permisos y versión al ejecutarse. | `test_academic.py`, `test_model_boundary.py` |
| Administrador | Administra las operaciones permitidas en su centro. La recuperación de recuerdos y vectores respeta la titularidad individual incluso con este rol. | `test_semantic03.py`, `test_operations03.py` |
| Invitado y demostración completa | Perfil público limitado con caducidad y cuotas. En la demo completa se puede cambiar entre tres roles del mismo centro ficticio. Otro visitante recibe su propio centro y archivos. La administración local del servidor queda restringida al perfil correspondiente. | `test_public_guest.py`, `test_teacher_demo.py`, `test_teacher_launch.py` |
| Acceso remoto y portal estático | El perfil Access comprueba identidad y su vinculación con la invitación. Pages prueba únicamente la conexión pública con el origen habilitado. Inicio de sesión y cookies permanecen en el origen del servidor. | `test_atlas_remote.py`, `test_pages_connection.py` |

## Contrato mínimo por operación

En el servidor, comprobar identidad activa, perfil de ejecución, rol, centro y relación con el recurso. Según la acción, verificar además CSRF, cuota, versión, plazo de acceso y confirmación. La captura de referencia debe registrar por separado éxito, sesión caducada, acción denegada y recurso ajeno oculto. Mantener el código 403 o 404 que ya observa el cliente en cada recorrido. [Resolución de sesión](../backend/app/auth.py) · [Permisos académicos](../backend/app/policy.py) · [Permisos de clase](../backend/app/class_policy.py).

El cliente envía la cookie al mismo origen y añade `X-CSRF-Token` en los cambios de estado. El servicio de una herramienta y la ruta HTTP deben verificar al mismo actor. Búsquedas, exportaciones, informes y descargas requieren el mismo filtrado que la lectura directa. La caché del navegador admite recursos estáticos y la copia pública prevista por la PWA. [Cliente HTTP](../frontend/src/api.ts) · [Service worker](../frontend/public/sw.js).

Para cada reemplazo se probarán dos centros y dos visitantes con identificadores y archivos diferentes. La matriz incluirá revocación entre propuesta y confirmación, reintentos, trabajo por equipos y lectura posterior al cambio de rol. Las pruebas usarán identidades sintéticas creadas en cada ejecución.
