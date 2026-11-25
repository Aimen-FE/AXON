# 0004 · Asignar un propietario a cada dato y regla

## Estado

Accepted

## Contexto

En 0.7 una herramienta del asistente llama directamente al manejador HTTP del listado de clases. Una matrícula de grupo y la pertenencia a una clase representan permisos diferentes. Si cada consumidor deduce por su cuenta qué puede ver un alumno, esos recorridos pueden divergir.

## Decisión

Cada dato y cada regla de negocio tienen un módulo propietario. Los demás solicitan la operación pública mínima y el propietario mantiene su SQL y sus comprobaciones de acceso. Los manejadores HTTP llaman al dominio. La IA, la CLI y los trabajos programados llaman directamente al mismo caso de uso. La composición conecta los colaboradores y mantiene las dependencias sin ciclos.

## Alternativas consideradas

Compartir modelos y consultas internas entre todos los dominios facilita una lectura puntual y dificulta cambiarla con garantías. Un paquete general de `utils` o `services` volvería a concentrar permisos y decisiones de varios propietarios.

## Consecuencias

Cambiar una consulta o invocarla desde el asistente conserva un punto responsable de su autorización. Un recorrido transversal requiere explicitar el contrato entre propietarios. El README del módulo identifica dependencias permitidas y prohibidas, y sus pruebas respaldan esa frontera.

## Referencias

[Catálogo de herramientas](../../backend/app/tools.py) · [Política de clases](../../backend/app/class_policy.py) · [Pruebas de clases](../../backend/tests/test_classes.py) · [Mapa de propietarios](../auditoria/0.8/modulos.md).
