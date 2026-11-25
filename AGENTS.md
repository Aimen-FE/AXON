# Trabajar en AXON

Leer primero este archivo y seguir únicamente los enlaces pertinentes a la tarea. Comprobar la fase autorizada y el estado del árbol de trabajo. Antes de editar, explicar brevemente el recorrido, los módulos y archivos afectados. Trabajar solo en esa fase. [Plan y estado](ROADMAP.md).

## Qué leer según la tarea

| Si se va a… | Consultar |
| --- | --- |
| Abrir una rama, hacer commits o enviar un PR | [Ramas y contribuciones de 0.8](CONTRIBUTING.md). |
| Diseñar o modificar un módulo | Su README, la [arquitectura y la ficha de módulo](ARCHITECTURE.md) y el [ADR pertinente](docs/decisions/README.md). |
| Tocar persistencia o autorización | [Datos y migraciones](docs/DATABASE.md) o [permisos y perfiles](docs/SECURITY.md), según el cambio. |
| Sustituir o retirar una vía de 0.7 | [Secuencia de migración y retirada](ROADMAP.md#secuencia-de-trabajo-de-cada-módulo) y [contrato de pruebas](docs/TESTING.md#contrato-de-sustitución). |

## Reglas de código y datos

- Usar inglés en variables, funciones, clases, tipos, módulos, nombres de archivos fuente nuevos, comentarios, docstrings, logs técnicos, mensajes internos, excepciones internas e interfaces entre módulos. Mantener los nombres de bibliotecas, protocolos, estándares, APIs públicas y campos heredados con contrato.
- Mantener en español los textos visibles y respetar las opciones de idioma existentes. Cuando facilite su mantenimiento, llevar esos textos a recursos de interfaz o de internacionalización. En Python usar `snake_case` para funciones y `PascalCase` para clases. En TypeScript usar `camelCase` para funciones y `PascalCase` para tipos y componentes.
- Dar a cada archivo una responsabilidad principal. Tomar 200–400 líneas como orientación. Al superar 500, revisar sus responsabilidades. Al superar 1000, justificar explícitamente su extensión en el PR y junto al módulo. Separar código cuando aclare el dominio, la interfaz o la reutilización, facilite las pruebas o reduzca el acoplamiento. La cuenta de líneas por sí sola no justifica una división.
- Reutilizar lo que esté probado, aplicar tipos y validar entradas. Introducir una abstracción o dependencia solo cuando resuelva una necesidad concreta. Seguir los límites públicos del módulo propietario. [ADR 0004](docs/decisions/0004-module-boundaries.md).
- Usar exclusivamente datos ficticios en pruebas, demos, ejemplos y documentación pública. El Centro Educativo Nébula es la referencia para centros, alumnado, docentes, documentos, horarios y calificaciones. Preparar los ejemplos en destinos independientes y preservar las instalaciones de usuarios.

## Al cerrar una tarea

Actualizar las guías afectadas y el [registro de cambios](CHANGELOG.md). Para una decisión arquitectónica nueva o modificada, registrar el ADR correspondiente. [Ciclo de los ADR](docs/decisions/README.md#mantener-un-registro).

En el informe final indicar qué cambió y en qué archivos, documentación actualizada, pruebas ejecutadas y omitidas con su motivo, decisión arquitectónica afectada (o indicar que se conserva), commit, PR y riesgos o pendientes. Usar las [categorías de evidencia](docs/TESTING.md#cómo-informar-de-los-resultados) y enlazar los resultados disponibles.
