# 0003 · Autenticar en el origen del servidor

## Estado

Accepted

## Contexto

La aplicación autenticada y su API comparten origen. GitHub Pages tiene otro origen y puede abrirse antes de que el visitante haya elegido un servidor.

## Decisión

Abrir la sesión en el servidor de AXON con cookie `HttpOnly`, `SameSite=Strict` y `Secure` para el acceso HTTPS externo. El servidor conserva la comprobación de origen y valida `X-CSRF-Token` en las operaciones autenticadas de escritura. Pages comprueba `/api/public/connection` sin credenciales y abre la aplicación en el origen elegido. El permiso CORS para esa consulta se limita al origen configurado.

## Alternativas consideradas

Una interfaz autenticada en Pages exigiría cookies entre sitios y CORS con credenciales, o un token accesible a JavaScript en el portal. Ambas opciones darían al portal responsabilidades sobre la sesión.

## Consecuencias

Pages puede comprobar disponibilidad y mostrar la opción de abrir AXON. El usuario inicia sesión en el servidor y la aplicación autenticada necesita que ese servidor esté disponible. Conservar los atributos de la cookie y la denegación del inicio de sesión desde otro origen en las pruebas de contrato.

## Referencias

[Emisión y validación de sesiones](../../backend/app/auth.py) · [Sonda pública](../../frontend/src/server-connection.ts) · [Pruebas de origen y cookies](../../backend/tests/test_pages_connection.py) · [Permisos](../SECURITY.md).
