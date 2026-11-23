"""Full AXON teacher origin, always on its own loopback port and database."""
from dataclasses import replace
import os,uvicorn
from .config import ROOT,Settings
from .main import create_app
from .teacher_launch import origin_port

def main():
    data=ROOT/'data/teacher-demo'
    settings=replace(Settings.from_env(),data_dir=data,database_url=f'sqlite:///{data}/axon.sqlite3',demo=True,remote_demo=False,public_demo=True,full_demo=True,cookie_secure=True,session_hours=24,ai_mode='ollama',ollama_model='llama3.2:3b',allowed_origins=(),public_origin_host=os.environ.get('AXON_PUBLIC_ORIGIN_HOST',''))
    application=create_app(settings)
    uvicorn.run(application,host='127.0.0.1',port=origin_port(),proxy_headers=False,access_log=False,limit_concurrency=32,timeout_keep_alive=5,timeout_graceful_shutdown=12)
if __name__=='__main__':main()
