#!/usr/bin/env python3
"""Install the reviewed connector locally; never authenticates or starts a tunnel."""
import argparse,hashlib,json,os,tempfile
from pathlib import Path
import httpx
VERSION='2026.11.0'
EXPECTED='51f7c68b57ed7269164075d7e789efce5b59355982f06392deeb037d982a51fd'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--download-public-connector',action='store_true',required=True);parser.parse_args()
    root=Path(__file__).resolve().parents[1];target=root/'data/tools';target.mkdir(parents=True,exist_ok=True,mode=0o700)
    with httpx.Client(timeout=30,follow_redirects=True,trust_env=False) as client:
        release=client.get('https://api.github.com/repos/cloudflare/cloudflared/releases/tags/'+VERSION);release.raise_for_status()
        asset=next(x for x in release.json()['assets'] if x['name']=='cloudflared-linux-amd64')
        if asset.get('digest')!='sha256:'+EXPECTED:raise ValueError('La huella de la publicación oficial ha cambiado')
        destination=target/'cloudflared'
        if destination.is_symlink():raise ValueError('No se modifica un enlace simbólico')
        if destination.exists():
            if hashlib.sha256(destination.read_bytes()).hexdigest()!=EXPECTED:raise ValueError('El conector local ha cambiado; no se sobrescribe')
        else:
            from sys import path
            path.insert(0,str(root/'backend'))
            from app.media_setup import download
            with tempfile.TemporaryDirectory(prefix='.connector-',dir=target) as temporary:
                temp=Path(temporary)/'cloudflared';download(asset['browser_download_url'],temp,EXPECTED,100*1024**2,client);temp.chmod(0o700);os.replace(temp,destination)
        manifest={'version':VERSION,'url':asset['browser_download_url'],'sha256':EXPECTED,'verified_against':'Official GitHub release asset digest','installed_inside_project':True,'tunnel_started':False}
        (target/'cloudflared-manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps({'connector_ready':True,'version':VERSION,'tunnel_started':False}))
if __name__=='__main__':main()
