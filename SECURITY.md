# Seguridad y privacidad

## Control de acceso

La primera cuenta se crea desde el servidor, con la base vacía y una contraseña elegida por el operador. El servidor no tiene un formulario de registro abierto. Los administradores pueden crear cuentas o cambiar roles dentro de su centro, con auditoría y cierre de sesiones afectadas. Los grupos y las asignaturas se validan en la API. El administrador del centro gestiona registros académicos autorizados. Las conversaciones y la memoria requieren la cuenta propietaria.

Los hashes de contraseñas usan Argon2id. Las sesiones son opacas, tienen caducidad y se guardan como hash en SQLite. Las cookies son HttpOnly y SameSite Strict y se requiere Secure para los nombres externos configurados. Las escrituras autenticadas validan CSRF y los orígenes configurados. El inicio de sesión limita fallos por usuario y red y aplica un límite agregado por red. Ajusta los límites de tu proxy a la carga.

## Contenido y servicios

Se limitan el tamaño de peticiones y documentos, los formatos permitidos y las extracciones. Los lectores de PDF/OCR/voz y matemáticas usan procesos acotados. Se valida acceso y procedencia antes de descargar documentos. El lector de URLs valida DNS, redirecciones y direcciones públicas, con límites de lectura. El asistente únicamente solicita herramientas registradas. Los argumentos, el rol y el ámbito se vuelven a validar en el servidor. Los cambios académicos pasan por una confirmación.

El worker solo guarda recursos estáticos servidos sin credenciales. Las peticiones API, incluidas las descargas autenticadas, no pasan por su caché. La copia sin conexión que se autoriza desde Configuración guarda un subconjunto de información ya pública durante siete días. Los formularios y las conversaciones requieren el servidor.

Las integraciones externas son opcionales. Los tokens OAuth se cifran con una clave del operador. Los respaldos incluyen la clave necesaria para recuperar integraciones y deben custodiarse en un lugar solo accesible al operador. El repositorio excluye configuraciones reales, documentos, datos, registros, modelos y copias.

## Demostración externa

La demo de profesor usa una base separada en loopback, un centro ficticio y archivos propios por visitante, y límites por sesión y agregados. El conector saliente publica esa instancia. Las sesiones temporales y cuotas no conceden acceso a la instalación de administración. Usa datos inventados al probarla. Consulta [instalación y HTTPS](INSTALL.md) y [Cloudflare](deploy/cloudflare/README.md).

## Reportar fallos

Si el repositorio habilita los avisos privados de seguridad, usa la opción **Report a vulnerability** en la pestaña Security. También puedes contactar por privado con quien administra tu instalación. Incluye versión, impacto, configuración relevante y pasos mínimos. Evita adjuntar datos reales, claves o cookies.
