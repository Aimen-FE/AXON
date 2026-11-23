# Verificar AXON

Compila el frontend y ejecuta `./scripts/test.sh` con una base temporal. Para probar el motor, inicia Ollama con el modelo configurado. Para OCR y voz se necesitan los componentes de [instalación](../INSTALL.md). La prueba de recuperación semántica usa `AXON_SEMANTIC_TEST_DATA` para leer los archivos públicos del modelo local.

En un perfil limpio de Chromium, abre la URL HTTPS o el loopback local. Verifica el manifiesto, el trabajador activado y el modo instalado. Instala AXON, abre su ventana, inicia sesión y comprueba que se conserva al recargar. Prueba también el acceso de alumno, profesor y administrador. Después de activar la emulación sin conexión, recarga para ver la pantalla informativa. Consulta el almacenamiento y comprueba que las respuestas personales no aparecen en la caché.

En un tamaño móvil, comprueba el menú al tocar fuera y con Escape, el acceso al compositor, los formularios y el foco. Activa la preferencia del sistema de movimiento reducido y verifica la navegación. Las rutas **Calendario**, **Tareas**, **Exámenes**, **Documentos** y **Configuración** conservan su funcionalidad con ambos ajustes.

Comparte los resultados con capturas hechas con datos inventados y sin direcciones temporales de un despliegue.

## Resultados de 0.7

- Instalación desde un clon limpio en Linux con Python 3.12.14, SQLite 3.53.1, Node.js 24 y pnpm 11.25.0. Base inicial vacía, asistente interactivo y compilación con dependencias descargadas desde los registros.
- 203 pruebas superadas con los recursos opcionales locales. El clon público sin modelos opcionales pasó 192 pruebas y omitió tres que necesitan OCR, transcripción o recuperación semántica. Los documentos del ensayo privado se quedan fuera del repositorio público, que incluye una prueba de importación con un DOCX inventado.
- Catorce comprobaciones con el servidor del clon y sus tres roles, incluida una respuesta real de Ollama, creación y confirmación de un examen y una tarea, descarga de material por grupo, cálculo, separación de conversaciones y persistencia de sesión y datos tras reiniciar.
- Chromium de escritorio aceptó el manifiesto. La instalación y reapertura, probadas con el protocolo de Chromium en un perfil persistente, conservaron la sesión en modo standalone. Al cortar la conexión apareció la pantalla informativa. La API y el HTML de sesión quedaron fuera de la caché. La guía para Safari se verificó con identificación de iPhone emulada.
- Vista móvil de 390 × 844 comprobada en Chromium. El menú aísla el foco, se cierra al tocar fuera y respeta el ajuste de movimiento reducido. La validación no incluye un dispositivo físico ni un teclado nativo de iOS.
- JavaScript inicial de 275,43 kB (86,62 kB comprimidos), frente a 449,54 kB (131,81 kB comprimidos) en la compilación anterior. El navegador de prueba registró una navegación inicial de unos 160 ms a través de loopback. El tiempo externo depende del equipo, su conexión y de la carga de Ollama.
- Auditoría del bloqueo de Python (68 paquetes) y de las dependencias de JavaScript, incluidas las de desarrollo. Después de actualizar cryptography a 50.0.0 y PyJWT a 2.15.0, las bases consultadas no informaron de avisos para las versiones revisadas.
