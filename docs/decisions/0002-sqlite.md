# 0002 · Conservar SQLite y una cadena Alembic común

## Estado

Accepted

## Contexto

Cada instalación dispone de un esquema con claves externas y búsqueda FTS5. Una actividad puede generar un evento de calendario y avisos en la misma operación. Copias de seguridad y demostraciones dependen de las relaciones entre las tablas.

## Decisión

Conservar SQLite y una única cadena de revisiones Alembic para el esquema de AXON. El caso de uso que inicia un cambio abre la transacción, comparte la sesión de base de datos con las operaciones participantes y confirma una vez al final. Ante un fallo, revierte la transacción completa.

## Alternativas consideradas

Una base por módulo exigiría coordinar la consistencia de los cambios y las restauraciones. Un servidor PostgreSQL sería una opción si la concurrencia exigiera otro motor, con un servicio adicional que instalar y mantener.

## Consecuencias

Actividad, calendario y avisos pueden guardarse de forma atómica. Las migraciones de distintos módulos deben acordar su orden y SQLite serializa las escrituras. Los archivos guardados en disco requieren limpieza si falla su operación y verificación propia al restaurar una copia.

## Referencias

[Configuración SQLite](../../backend/app/db.py) · [Cadena Alembic](../../backend/migrations/versions) · [Datos y restauración](../DATABASE.md) · [Pruebas de copia](../../backend/tests/test_backup.py).
