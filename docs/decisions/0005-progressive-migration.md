# 0005 · Sustituir recorridos de forma progresiva

## Estado

Accepted

## Contexto

AXON 0.7 es la referencia funcional. Su especificación enumera las rutas, pero deja abiertos los campos de las respuestas de éxito. Los datos visibles, la autorización y los efectos en disco forman parte del comportamiento que se quiere preservar.

## Decisión

Migrar un recorrido observable cada vez. Caracterizarlo en 0.7 con datos ficticios, ejecutar ambas implementaciones sobre estados iniciales equivalentes y comparar resultados por rol y centro. Activar un solo escritor. Retirar la vía anterior tras comprobar consumidores, equivalencia y retorno según el plan.

## Alternativas consideradas

Una sustitución completa aplazaría la detección de diferencias hasta la integración. Reorganizar archivos mantendría un historial sencillo, pero por sí solo no comprobaría si una entrega sigue visible solo para sus destinatarios.

## Consecuencias

Cada PR tiene un resultado comprobable y un punto de retorno. Durante la transición se mantienen dos implementaciones del recorrido elegido. Las comparaciones de escrituras necesitan copias independientes y datos de prueba reproducibles.

## Referencias

[Inventario de la API](../auditoria/0.8/http.tsv) · [Contrato de pruebas](../TESTING.md) · [Secuencia y retorno](../../ROADMAP.md).
