# Contribuir a AXON

## Ramas y PR de AXON 0.8

`main` representa siempre la última versión estable y recibe los cambios de 0.8 exclusivamente mediante el PR final. El desarrollo se realiza en ramas de trabajo. `rewrite/axon-v0.8` es la rama de integración de la edición 0.8.

| Trabajo | Rama de partida | Destino del PR |
| --- | --- | --- |
| Una fase o un cambio relevante, incluida documentación | `rewrite/axon-v0.8` actualizada | `rewrite/axon-v0.8` |
| Integración final de la edición | `rewrite/axon-v0.8` terminada y verificada | `main` |

Crear una rama por fase o cambio coherente. Por ejemplo, `rewrite/0.8-phase-1-foundations` para los fundamentos o `feature/0.8-classes` para un cambio de clases. Separar módulos sin relación en PR distintos. Verificar la rama de destino antes de enviar el PR. Proponer la integración en `main` únicamente al cumplir los criterios finales del [plan](ROADMAP.md). Preservar el historial compartido.

## Commits

Hacer commits pequeños, descriptivos, de una sola intención y reversibles cuando sea razonable. `Add class listing characterization tests` y `Extract class read service behind module interface` describen dos cambios que se pueden revisar y revertir por separado. Incluir en cada commit las pruebas o la documentación de esa misma intención. Separar las refactorizaciones, funcionalidades y correcciones de documentación que persigan objetivos distintos.

## Preparar la revisión

1. Preparar una [instalación local](INSTALL.md) y una base ficticia. Describir el comportamiento y los módulos o roles afectados.
2. Seguir el orden de compilación y pruebas de la [guía de verificación](docs/TESTING.md). Si cambia la interfaz, comprobar escritorio, móvil, teclado y movimiento reducido. Para permisos o datos, probar también la API con una cuenta autorizada y otra ajena.
3. Abrir el PR con el alcance, resultados, servicios opcionales y forma de retorno cuando proceda. Integrar tras la revisión y con los controles obligatorios aprobados. [Informe de cierre](AGENTS.md#al-cerrar-una-tarea).

Escribe una migración Alembic nueva al cambiar el esquema. Incluye fecha y procedencia en fuentes verificadas. Conserva los permisos del servidor al cambiar la interfaz. Evita subir archivos de datos, configuraciones reales, evidencias de un despliegue concreto y capturas con sesiones. Si detectas un problema de seguridad, sigue [el canal de comunicación privado](SECURITY.md).
