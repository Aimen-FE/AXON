# Decisiones de arquitectura de AXON

Cada registro (ADR) explica una decisión, sus alternativas y el coste que aceptamos. El estado indica si se ha adoptado el criterio de diseño. El avance de su implementación se sigue en el plan. [Mapa de módulos](../auditoria/0.8/modulos.md) · [Plan de migración](../../ROADMAP.md) · [Guía de trabajo](../../AGENTS.md).

| ADR | Decisión que permite recuperar |
| --- | --- |
| [0001 · Monolito modular](0001-modular-monolith.md) | Cómo se despliega el servidor y dónde están sus límites de proceso. |
| [0002 · SQLite y Alembic](0002-sqlite.md) | Quién confirma una operación que escribe en varios módulos. |
| [0003 · Autenticación en el mismo origen](0003-same-origin-authentication.md) | Dónde se abre la sesión y qué puede consultar GitHub Pages. |
| [0004 · Propiedad de datos y reglas](0004-module-boundaries.md) | Qué módulo toma una decisión y cómo la usan sus consumidores. |
| [0005 · Migración progresiva](0005-progressive-migration.md) | Qué evidencia permite sustituir un recorrido de 0.7. |

## Mantener un registro

Usar un número consecutivo y un nombre de archivo en inglés. Incluir título, estado, contexto, decisión, alternativas consideradas, consecuencias y referencias al código, pruebas o PR pertinentes. Un vínculo a la guía técnica evita copiarla aquí.

`Proposed` identifica una decisión abierta, `Accepted` una acordada y `Rejected` una descartada. Si cambia una decisión aceptada, crear el ADR sucesor, marcar el anterior como `Superseded` al aceptar el relevo y enlazar ambos en los dos sentidos. Una aclaración que conserve la decisión se puede editar en el mismo registro.
