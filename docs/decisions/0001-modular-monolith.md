# 0001 · Mantener AXON como monolito modular

## Estado

Accepted

## Contexto

AXON se instala en un ordenador y sirve la aplicación y la API con FastAPI. Publicar una actividad de clase coordina su estado, sus fechas y los avisos a los miembros.

## Decisión

Mantener un servidor desplegable con módulos de dominio que exponen operaciones públicas. GitHub Pages conserva su despliegue estático. Ollama, el túnel y los procesos de tratamiento de archivos mantienen sus límites de ejecución.

## Alternativas consideradas

Separar los dominios en microservicios permitiría desplegarlos individualmente, a costa de coordinar escrituras y fallos de red en una operación académica. Mantener la organización interna de 0.7 dejaría las dependencias cruzadas que detectó la auditoría.

## Consecuencias

La instalación y las pruebas de un recorrido completo siguen siendo locales. Los módulos del servidor se publican juntos y comparten ciertos fallos de proceso. Sus límites requieren interfaces explícitas y comprobaciones de dependencias.

## Referencias

[Arranque actual](../../backend/app/main.py) · [Publicación de actividades](../../backend/app/classwork.py) · [Mapa de módulos](../auditoria/0.8/modulos.md).
