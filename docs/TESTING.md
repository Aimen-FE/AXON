# Pruebas de referencia

## Resultados de la auditoría del 25 de noviembre de 2026

Se ensayó el [commit estable](https://github.com/Aimen-FE/AXON/commit/80fef73e734768593292a2dd20eda89755ebeaba) en una exportación temporal con Python 3.12.14, SQLite 3.53.1, Node 24.22.3, TypeScript 5.9.3 y Vite 7.3.8. Las bases, archivos de usuarios y perfiles de navegador de prueba se crearon para esta ejecución.

| Ensayo | Resultado observado |
| --- | --- |
| Pytest antes de colocar la compilación local en `frontend/dist` | 204 aprobadas, 2 fallidas, 3 omitidas. Las dos fallidas esperan HTTP 200 en `/` y recibieron 404. Fueron `test_frontend_and_pwa_assets_are_served` y `test_public_origin_fails_closed_and_has_no_normal_login`. |
| TypeScript y compilaciones de Vite | Pasaron el tipado, la compilación local y la de Pages. La comprobación de Pages validó rutas, manifiesto, alcance, iconos, recursos y página sin conexión. |
| Pytest con la compilación local disponible | 206 aprobadas y 3 omitidas. Las opcionales necesitan los modelos de OCR en español, voz y vectores multilingües. |
| Pytest completo con los modelos locales | **209 aprobadas, 0 omitidas, 0 fallidas** en 70,29 s. Starlette emitió un aviso de obsolescencia por el uso de httpx con su cliente de pruebas. |
| Portal en Chrome con perfil nuevo | Se cargó `/AXON/`, se activó el service worker y se recargó con la red desconectada. Siguió visible «Tu espacio educativo». El manifiesto declaró `standalone` con alcance `/AXON/`. Se observaron 13 recursos en caché, todos fuera de la API. |

Esta medición cubre el navegador de escritorio y el artefacto de Pages servido en local. La instalación física en iOS o Android, una conversación con Ollama real, la disponibilidad de un túnel externo y las cuentas reales de terceros quedan fuera de esta prueba. El protocolo del modelo y los perfiles públicos tienen pruebas con sustitutos.

## Cómo repetir las pruebas

Trabajar en una copia de la revisión elegida. Usar Python 3.12 en un entorno virtual, Node 24 y pnpm 11. Los comandos siguientes se ejecutan desde la raíz de esa copia. La compilación normal debe seguir en `frontend/dist` cuando arranque pytest. Pages escribe en una carpeta aparte.

```bash
export AXON_SKIP_DOTENV=true
python -m pip install -r backend/requirements.lock
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend run build
pages_dir=$(mktemp -d)
pnpm --dir frontend exec vite build --mode pages --outDir "$pages_dir"
python -m pytest -rs backend/tests
```

Para incluir las tres pruebas opcionales, indicar en `AXON_MEDIA_MODELS_DIR` la carpeta de modelos de OCR y Vosk, y en `AXON_SEMANTIC_TEST_DATA` un directorio temporal con el subdirectorio `models` y su `semantic-model.json`. Para comprobar voz se necesitan eSpeak NG y FFmpeg. Se puede enlazar la carpeta de modelos existente a ese directorio de ensayo. Las bases y los archivos de trabajo de las pruebas siguen siendo temporales.

## Cobertura existente y pruebas que faltan para la migración

| Área | Evidencia disponible en [la batería](../backend/tests) | Ampliación antes del reemplazo |
| --- | --- | --- |
| Identidad y perfiles | `test_installation`, `test_security`, `test_public_guest`, `test_teacher_demo`, `test_atlas_remote` | Comparar cookies, caducidad, revocación, cuotas y códigos de denegación de ambos sistemas con la misma matriz de actores. |
| Educación y clases | `test_nebula`, `test_classes`, `test_academic` verifican matrícula, admisión, equipos, entregas, guías, calificaciones y horarios | Comparar en el mismo centro las tareas históricas y nativas, las revisiones y el calendario tras un reintento. |
| Asistente, memoria y fuentes | `test_model_boundary`, `test_agent03`, `test_memory_chat`, `test_semantic03`, `test_learning_security`, `test_documents`, `test_atlas_providers` | Comparar herramientas permitidas, citas, permisos y efectos persistidos con respuestas del modelo fijadas. En aceptación local, comprobar además un diálogo Ollama. |
| Trabajos, informes y administración | `test_operations`, `test_operations03`, `test_backup`, `test_teacher_launch`, `test_portable_import` | Simular interrupción durante una transacción y reanudación del trabajo. Restaurar en un segundo directorio y comparar documentos, FTS y aislamiento. |
| Aplicación y Pages | `test_pages_connection`, `test_operations` y el [verificador del artefacto](../frontend/scripts/check-pages.mjs) cubren orígenes, rutas y archivos | Automatizar en CI el recorrido actual en navegador y la actualización entre dos versiones de caché. Ensayar identificación y cierre de sesión en el origen de la aplicación y apertura instalada en dispositivos reales. |

## Contrato de sustitución

Antes de cambiar un recorrido, ejecutarlo en 0.7 con datos ficticios y guardar petición, actor, centro, estado inicial, respuesta y estado final. Repetirlo en el candidato desde condiciones equivalentes. Cubrir éxito y errores, distintos roles, acceso a recursos ajenos y aislamiento entre dos centros.

| Comparación | Evidencia que se conserva |
| --- | --- |
| Respuesta HTTP | Código, campos JSON, tipos y orden de resultados, cuerpo de error, cabeceras relevantes y atributos de cookie. |
| Visibilidad y archivos | Recursos, campos y adjuntos que ve cada actor, permisos denegados, nombre, tipo y bytes de las descargas. |
| Efectos persistentes | Altas y cambios de filas, relaciones, archivos guardados y avisos por destinatario. Verificar el estado después de un fallo o reintento cuando corresponda. |

Normalizar únicamente identificadores generados y reloj mediante correspondencias explícitas. Si un 200 devuelve una entrega ajena o genera dos avisos, la comparación falla. Toda diferencia intencionada necesita contrato, consumidores y prueba actualizados. [Decisión de migración](decisions/0005-progressive-migration.md).

## GitHub Actions desde la fase 1

Cada PR de 0.8 deberá activar comprobaciones de GitHub Actions para su rama de destino. Conservar el despliegue de Pages en su propio flujo. El mínimo obligatorio comprende lo siguiente.

1. Usar las versiones de Python y Node indicadas en esta guía e instalar las dependencias fijadas del servidor y del cliente. [Dependencias del servidor](../backend/requirements.lock) · [Dependencias del frontend](../frontend/pnpm-lock.yaml).
2. Comprobar tipado y calidad, compilar la aplicación en `frontend/dist` y compilar Pages en otro directorio con el verificador de su artefacto.
3. Arrancar con una base vacía, ejecutar la batería backend tras la compilación local y las pruebas de contrato del módulo modificado.
4. Ejecutar los controles de arquitectura ya introducidos en 0.8, incluidas las restricciones de dependencias que se hayan incorporado. Vincular los resultados obligatorios al commit del PR antes de integrarlo.

Las pruebas que necesitan modelos pesados o hardware local se ejecutan como aceptación separada. Registrar el equipo o modelo necesario y el resultado real, también cuando falte ese recurso.

## Cómo informar de los resultados

| Categoría | Qué indicar en el PR y en el cierre |
| --- | --- |
| CI verificado | Enlace a la ejecución de GitHub Actions para el commit y conclusión de sus trabajos. |
| Prueba local | Comando o comprobación automatizada ejecutada en el equipo, revisión y resultado. |
| Prueba manual | Recorrido hecho por una persona, entorno y observación comprobada. |
| Prueba no realizada | Comprobación pendiente u omitida y motivo concreto. |
