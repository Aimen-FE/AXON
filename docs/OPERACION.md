# Operación de AXON

El operador conserva la base SQLite y la carpeta `uploads` fuera del directorio de archivos públicos. Crea una copia con la aplicación detenida cuando necesites una instantánea coherente de ambos. Desde la raíz del proyecto:

```bash
./scripts/backup.sh /ruta/privada/axon.zip --server-stopped
./scripts/restore.sh /ruta/privada/axon.zip /ruta/privada/restauracion-nueva
```

La restauración comprueba integridad y claves externas. Usa una carpeta nueva para revisarla. Las copias de la interfaz administrativa también requieren permisos de operador sobre el sistema de archivos para su recuperación.

El importador académico trabaja con información del titular. Prepara un manifiesto y sus originales fuera del repositorio y revisa sus opciones desde `backend/app/academic_import.py`. Indica año y procedencia, distingue asignaturas seleccionadas de alternativas y revisa los resultados antes de utilizarlos.

```bash
PYTHONPATH=backend .venv/bin/python -m app.cli import-academic /ruta/privada/manifiesto.json
PYTHONPATH=backend .venv/bin/python -m app.cli setup-link USUARIO
```

El segundo comando emite un enlace de un solo uso para una cuenta privada aún inactiva. Entrégalo por un canal privado al titular. Si la cuenta ya está activa, utiliza el restablecimiento local descrito en [la instalación](../INSTALL.md).

Los registros y las copias deben permanecer con permisos restringidos. Programa las revisiones institucionales desde la cuenta autorizada. Para las pruebas, usa otra base.
