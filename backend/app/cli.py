import argparse
import os
from datetime import datetime,timezone
from pathlib import Path
from .config import Settings,ROOT


def main():
    parser=argparse.ArgumentParser(description='AXON · gestión local')
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('init',help='Preparar una base sin cuentas ni datos de ejemplo')
    commands.add_parser('setup-admin',help='Configurar el primer centro y administrador desde esta terminal')
    reset = commands.add_parser('reset-access',help='Restablecer localmente la contraseña de una cuenta activa')
    reset.add_argument('username')
    demo = commands.add_parser('init-demo',help='Crear cuentas ficticias con claves generadas en una base separada')
    demo.add_argument('directory',type=Path)
    semantic=commands.add_parser('setup-semantic',help='Preparar explícitamente el modelo semántico público dentro de AXON')
    semantic.add_argument('--download-public-model',action='store_true',required=True,help='Autoriza la descarga pública del modelo; no se usan credenciales guardadas')
    media=commands.add_parser('setup-media',help='Preparar explícitamente los modelos públicos de OCR y dictado dentro de AXON')
    media.add_argument('--download-public-models',action='store_true',required=True)
    serve=commands.add_parser('serve',help='Iniciar en localhost')
    serve.add_argument('--port',type=int,default=None)
    serve.add_argument('--reload',action='store_true')
    back=commands.add_parser('backup',help='Crear copia; detener AXON antes')
    back.add_argument('output',nargs='?')
    back.add_argument('--server-stopped',action='store_true',required=True,help='Confirmas que has detenido el servidor antes de copiar')
    restore_parser=commands.add_parser('restore',help='Restaurar una copia en una carpeta nueva')
    restore_parser.add_argument('archive')
    restore_parser.add_argument('destination')
    academic=commands.add_parser('import-academic',help='Importar un manifiesto privado y preparar el enlace de contraseña')
    academic.add_argument('manifest')
    setup=commands.add_parser('setup-link',help='Renovar el enlace privado de una cuenta sin activar')
    setup.add_argument('username')
    args=parser.parse_args()
    settings=Settings.from_env()
    if args.command in ('setup-admin', 'reset-access', 'init-demo'):
        import sys
        from pydantic import ValidationError
        from .installation import create_first_admin, create_local_demo, prompt_password, reset_password
        previous_mask = os.umask(0o077)
        try:
            if args.command == 'setup-admin':
                if not sys.stdin.isatty():
                    raise ValueError('Ejecuta el asistente desde una terminal interactiva.')
                print('Configuración inicial de AXON')
                center = input('Nombre del centro: ')
                town = input('Localidad (opcional): ')
                username = input('Usuario administrador: ').strip()
                display_name = input('Nombre visible: ')
                create_first_admin(settings, center, town, username, display_name, prompt_password())
                print('Administrador creado. Inicia AXON y entra con tu nueva cuenta.')
            elif args.command == 'reset-access':
                reset_password(settings, args.username, prompt_password())
                print('Contraseña cambiada y sesiones anteriores cerradas.')
            else:
                credentials = create_local_demo(settings, args.directory)
                print(f'Cuentas ficticias creadas. Sus credenciales se guardaron en {credentials}.')
        except ValidationError as exc:
            fields = ', '.join(str(error['loc'][0]) for error in exc.errors(include_input=False))
            parser.error('Revisa los campos: ' + fields)
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
        except (EOFError, KeyboardInterrupt):
            parser.exit(1, 'Operación cancelada.\n')
        finally:
            os.umask(previous_mask)
    elif args.command=='setup-media':
        import json
        from .media_setup import setup_media
        print(json.dumps(setup_media(),ensure_ascii=False,indent=2))
    elif args.command=='setup-semantic':
        import json
        from .model_setup import setup_semantic
        print(json.dumps(setup_semantic(settings),ensure_ascii=False,indent=2))
    elif args.command=='import-academic':
        import json
        from .main import create_app
        from .academic_import import provision_bundle
        app=create_app(settings,maintenance=False)
        try:
            with app.state.session_factory() as db:result=provision_bundle(db,settings,json.loads(Path(args.manifest).read_text()))
            print(json.dumps(result,ensure_ascii=False,indent=2))
        finally:app.state.engine.dispose()
    elif args.command=='setup-link':
        import secrets
        from datetime import timedelta
        from sqlalchemy import select,delete
        from .main import create_app
        from .models import User,AccountSetup
        from .db import utcnow
        from .auth import digest
        app=create_app(settings,maintenance=False)
        try:
            with app.state.session_factory() as db:
                user=db.scalar(select(User).where(User.username==args.username.lower()))
                if not user or user.active or user.is_demo:parser.error('Solo se renuevan enlaces de cuentas privadas aún sin activar')
                db.execute(delete(AccountSetup).where(AccountSetup.user_id==user.id))
                token=secrets.token_urlsafe(40);db.add(AccountSetup(user_id=user.id,token_hash=digest(token),expires_at=utcnow()+timedelta(hours=24)));db.commit()
                file=settings.data_dir/'private-account-setup.txt';file.write_text('http://127.0.0.1:8000/#setup='+token+'\n');file.chmod(0o600)
                print('Enlace privado guardado en '+str(file))
        finally:app.state.engine.dispose()
    elif args.command=='init':
        from .main import create_app
        app=create_app(settings,maintenance=False)
        app.state.engine.dispose()
        print('Base de datos preparada. No se han sobrescrito datos existentes.')
    elif args.command=='serve':
        import uvicorn
        host=os.getenv('AXON_HOST','127.0.0.1')
        if host not in ('127.0.0.1','localhost','::1'):parser.error('Este prototipo solo permite escuchar en localhost')
        uvicorn.run('app.main:app_factory',factory=True,host=host,port=args.port or int(os.getenv('AXON_PORT','8000')),reload=args.reload,access_log=False)
    elif args.command=='backup':
        from .backup import backup
        output=args.output or str(ROOT/'backups'/('axon-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.zip'))
        try:print(backup(settings,output))
        except (ValueError,OSError) as exc:parser.error(str(exc))
    elif args.command=='restore':
        from .backup import restore
        try:print(restore(args.archive,args.destination))
        except (ValueError,OSError) as exc:parser.error(str(exc))


if __name__=='__main__':main()
