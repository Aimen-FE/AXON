# Lanzador de AXON para Linux

El acceso directo **AXON** inicia Ollama si hace falta, abre el espacio privado local y pone en marcha la demostración pública aislada. Comprueba el enlace HTTPS y abre la web en el navegador predeterminado. Si ya está en marcha, conserva el enlace y reutiliza los servicios.

Instalación del icono en el menú de aplicaciones y la carpeta Escritorio del usuario:

```bash
.venv/bin/python scripts/install-launcher.py
```

También puede ejecutarse `./AXON` desde el proyecto. No es necesario abrir una terminal para utilizar el icono. La ventana de preparación se cierra automáticamente y los servicios siguen funcionando cuando cierras el navegador. No instala programas ni configura inicio automático al encender el equipo.

En el menú contextual del icono figuran «Abrir mi espacio privado», «Detener demostración pública» y «Detener AXON y el enlace». El primero abre solo la instalación personal. El segundo cierra el túnel de demostración y sus invitados, conservando el espacio privado y Ollama. La tercera opción detiene además el AXON privado iniciado por este ejecutable; conserva un servicio compartido de Ollama. Los controles públicos siguen disponibles en el panel privado.

El enlace actual se abre automáticamente; puedes copiarlo de la barra del navegador. También está en `data/teacher-launch/enlace-publico.txt`; el lanzador conserva su copia al abrir la aplicación. Si se ha detenido Cloudflare o se ha apagado el ordenador, puede cambiar al iniciar la próxima vez. El archivo solo se actualiza tras verificar la respuesta pública real. No uses una dirección antigua que hayas guardado como favorito.

El ordenador debe permanecer encendido y conectado para compartir la demostración. Tras apagarlo, vuelve a abrir **AXON**. Este lanzador conserva la ejecución local: no contrata alojamiento, no abre puertos del router y no cambia las protecciones del perfil público.

Los registros de inicio quedan bajo `data/launcher/`, con permisos privados. Si una dirección está ocupada por otra aplicación, el lanzador informa del problema sin detener ese proceso. Una segunda pulsación no duplica servicios. Si falta el modelo previamente instalado, se informa y no se descarga otro ni se cambia de proveedor.

Para revisar el arranque sin abrir ventanas o navegador:

```bash
./AXON --no-window --no-browser
./AXON --status
./AXON --stop-demo --no-window
./AXON --stop-all --no-window
```

Cuando Ollama está instalado como servicio del equipo, el lanzador utiliza ese servicio y su carpeta de modelos. No crea una biblioteca vacía ni descarga otra copia. Si el sistema no permite iniciar un servicio detenido sin autorización, informa del motivo; normalmente Ollama ya arranca al encender este equipo.

La publicación actual utiliza la aplicación completa y crea una sesión de profesor y un centro ficticio propios por visitante. El supervisor mantiene la aplicación pública y el túnel activos sin corte programado y sin depender de la terminal. Comprueba cada minuto la respuesta pública y recupera fallos de los procesos; puede cambiar la URL. La sesión individual de 24 horas no limita la duración del enlace. El ordenador debe permanecer encendido, conectado y sin suspensión. Quick Tunnels no ofrece garantía de disponibilidad.

Si el túnel cae, abre de nuevo **AXON** y comparte la URL que se abra; puedes forzar un nuevo arranque con `PYTHONPATH=backend .venv/bin/python -m app.teacher_launch restart`. No reutilices una URL anterior tras el cambio. El primer arranque espera hasta seis minutos a que el nombre temporal se propague en DNS.

Para detener también el servicio compartido de Ollama, después de detener AXON, utiliza `systemctl stop ollama.service`; el sistema puede pedir autorización. No se cambia su configuración ni su inicio automático. Los procesos ajenos o no registrados no se cierran.
