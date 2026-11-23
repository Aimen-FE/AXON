"""The public origin; always loopback and always the isolated fictitious database."""
from dataclasses import replace
from pathlib import Path
import os,uvicorn
from .config import ROOT,Settings
from .main import create_app

def main():
    data=ROOT/'data/atlas-demo'
    settings=replace(Settings.from_env(),data_dir=data,database_url=f'sqlite:///{data}/axon.sqlite3',demo=True,remote_demo=False,public_demo=True,ai_mode='ollama',cookie_secure=True,allowed_origins=(),session_hours=1,max_upload=64*1024,public_origin_host=os.environ.get('AXON_PUBLIC_ORIGIN_HOST',''))
    application=create_app(settings)
    uvicorn.run(application,host='127.0.0.1',port=8015,proxy_headers=False,access_log=False,limit_concurrency=24,timeout_keep_alive=5)
if __name__=='__main__':main()
