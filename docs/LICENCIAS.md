# Licencias de AXON y sus componentes

Los archivos de código y documentación propios de AXON se distribuyen bajo [MIT](../LICENSE). Mantén el aviso de copyright y el texto de la licencia al redistribuirlos.

El repositorio distribuye fuentes propias y el tipo de letra Adwaita Sans. La fuente mantiene el aviso y las condiciones de [SIL OFL 1.1](../frontend/public/fonts/AdwaitaSans-LICENSE.txt). El repositorio no incluye documentos institucionales, paquetes instalados, ejecutables externos ni pesos de modelos. Los documentos de demostración se redactan expresamente para AXON. Las fuentes y componentes externos conservan las condiciones de sus titulares.

## Inventario revisado

Se contrastaron los metadatos de las 68 distribuciones fijadas para Python y 83 paquetes de Node.js instalados en Linux x86-64. Las versiones reproducibles están en los archivos de bloqueo.

| Componentes | Términos principales |
| --- | --- |
| FastAPI, SQLAlchemy, React, React DOM, Vite y Tailwind | MIT |
| Starlette, Uvicorn, SymPy, psutil y lxml | BSD |
| Lucide | ISC en lucide-react 0.468.0 |
| TypeScript, FastEmbed y Vosk | Apache 2.0 |
| ONNX Runtime | MIT, con avisos propios |
| Certifi, tqdm y Lightning CSS | MPL 2.0 o combinación declarada por el paquete |
| caniuse-lite y graceful-fs | CC BY 4.0 y Blue Oak 1.0.0, respectivamente |
| py-rust-stemmers | MIT según su repositorio oficial |

Si redistribuyes una compilación con dependencias, conserva sus licencias y avisos tal como entrega cada proveedor. En particular, revisa atribución y términos de los componentes con MPL 2.0 o CC BY 4.0. Ollama y los modelos seleccionados conservan sus propios términos de uso. Los binarios y modelos opcionales no se incluyen en este repositorio.

Fuentes: [licencia de Lucide](https://github.com/lucide-icons/lucide/blob/main/LICENSE), [licencia de Certifi](https://github.com/certifi/python-certifi/blob/master/LICENSE) y [licencia de py-rust-stemmers](https://github.com/qdrant/py-rust-stemmers/blob/master/LICENSE).
