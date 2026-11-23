# Contribuir a AXON

1. Prepara una [instalación local](INSTALL.md) y usa una base de pruebas con datos inventados.
2. Crea una rama para el cambio. Describe el comportamiento y qué módulos o roles afecta.
3. Ejecuta `./scripts/test.sh`. Si cambias la interfaz, comprueba escritorio, móvil, teclado y movimiento reducido. Para permisos o datos, comprueba también la API y las cuentas que deben quedar fuera.
4. Abre una propuesta de cambio con el resultado y las pruebas. Indica las funciones que requieren servicios opcionales.

Escribe una migración Alembic nueva al cambiar el esquema. Incluye fecha y procedencia en fuentes verificadas. Conserva los permisos del servidor al cambiar la interfaz. Evita subir archivos de datos, configuraciones reales, evidencias de un despliegue concreto y capturas con sesiones. Si detectas un problema de seguridad, sigue [el canal de comunicación privado](SECURITY.md).
