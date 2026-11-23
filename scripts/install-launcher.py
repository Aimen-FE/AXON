#!/usr/bin/env python3
"""Install only this user's AXON launchers; no autostart or system-wide changes."""
from pathlib import Path
import os,subprocess,shutil
ROOT=Path(__file__).resolve().parents[1]

def entry(root):
    quoted=str(root/'AXON').replace('\\','\\\\').replace('"','\\"')
    return f'''[Desktop Entry]
Version=1.0
Type=Application
Name=AXON
Comment=Iniciar AXON completo, Ollama y Cloudflare
Exec="{quoted}"
Path={root}
Icon={root}/frontend/public/icon.svg
Terminal=false
StartupNotify=false
Categories=Education;
Actions=Private;StopDemo;StopAll;
X-AXON-Launcher=true

[Desktop Action Private]
Name=Abrir mi espacio privado
Exec="{quoted}" --private

[Desktop Action StopDemo]
Name=Detener demostración pública
Exec="{quoted}" --stop-demo

[Desktop Action StopAll]
Name=Detener AXON y el enlace
Exec="{quoted}" --stop-all
'''

def install():
    if not (ROOT/'AXON').is_file() or not (ROOT/'.venv/bin/python').exists():raise RuntimeError('Falta el ejecutable o la instalación de AXON')
    home=Path.home();desktop=home/'Escritorio'
    if shutil.which('xdg-user-dir'):
        result=subprocess.run(['xdg-user-dir','DESKTOP'],capture_output=True,text=True,check=True)
        candidate=Path(result.stdout.strip())
        if not candidate.is_absolute() or candidate==home or not candidate.is_relative_to(home):raise RuntimeError('No se ha localizado una carpeta de escritorio independiente')
        desktop=candidate
    data=entry(ROOT);targets=[home/'.local/share/applications/axon.desktop',desktop/'AXON.desktop']
    for path in targets:
        if path.is_symlink():raise RuntimeError('No se sustituye un enlace existente: '+str(path))
        if path.exists() and 'X-AXON-Launcher=true' not in path.read_text():raise RuntimeError('Ya existe otro acceso directo: '+str(path))
    (ROOT/'AXON').chmod(0o700)
    for path in targets:
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(data);path.chmod(0o755)
        if shutil.which('desktop-file-validate'):subprocess.run(['desktop-file-validate',str(path)],check=True)
        if shutil.which('gio'):subprocess.run(['gio','set','-t','string',str(path),'metadata::trusted','true'],capture_output=True)
        print(path)
if __name__=='__main__':
    import argparse
    argparse.ArgumentParser(description='Instalar el icono AXON solo para tu usuario').parse_args()
    install()
