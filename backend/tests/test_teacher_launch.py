"""Supervision and credential boundaries of the public full application."""
from app import teacher_launch as launch


def test_public_environment_never_inherits_owner_provider_or_auth_secrets(monkeypatch,tmp_path):
    monkeypatch.setattr(launch,'ROOT',tmp_path)
    for name in ('GEMINI_API_KEY','GROQ_API_KEY','AXON_DATABASE_URL','AXON_CLASSROOM_CLIENT_SECRET','AXON_SEARCH_URL','CF_ACCESS_TOKEN','UNRELATED_SECRET'):
        monkeypatch.setenv(name,'owner-secret-fixture')
    monkeypatch.setenv('AXON_DATABASE_URL','sqlite:////private/owner.sqlite3')
    env=launch.safe_env()
    assert 'owner-secret-fixture' not in env.values()
    assert env['AXON_SKIP_DOTENV']=='true'
    assert env['AXON_DATABASE_URL']==f'sqlite:///{tmp_path}/data/teacher-demo/axon.sqlite3'
    assert env['AXON_OLLAMA_MODEL']=='llama3.2:3b'
    assert env['AXON_COOKIE_SECURE']=='true'


def test_supervisor_recovers_crash_and_obeys_explicit_stop(tmp_path,monkeypatch):
    monkeypatch.setattr(launch,'ROOT',tmp_path)
    launch.write(launch.folder()/'control.json',{'desired_running':True})
    events=[]
    monkeypatch.setattr(launch,'status',lambda:{'running':False,'url':None})
    monkeypatch.setattr(launch,'stop_children',lambda:events.append('stop'))
    def restart():
        events.append('restart')
    monkeypatch.setattr(launch,'start_children',restart)
    def stop_loop(n):
        control=launch.read(launch.folder()/'control.json');control['desired_running']=False;launch.write(launch.folder()/'control.json',control)
    monkeypatch.setattr(launch.time,'sleep',stop_loop)
    launch.monitor()
    assert events==['stop','restart']
    assert launch.read(launch.folder()/'control.json')['connection_changes']==1
    launch.monitor()
    assert events==['stop','restart']


def test_healthy_supervisor_never_stops_due_to_old_start_time(tmp_path,monkeypatch):
    monkeypatch.setattr(launch,'ROOT',tmp_path)
    launch.write(launch.folder()/'control.json',{'desired_running':True})
    monkeypatch.setattr(launch,'status',lambda:{'running':True,'url':'https://fixture.trycloudflare.com','started_at':'2000-01-01T00:00:00+00:00'})
    monkeypatch.setattr(launch,'public_ready',lambda url:True)
    def stop_loop(n):launch.write(launch.folder()/'control.json',{'desired_running':False})
    monkeypatch.setattr(launch.time,'sleep',stop_loop)
    def forbidden():raise AssertionError('A healthy tunnel was stopped due to age')
    monkeypatch.setattr(launch,'stop_children',forbidden)
    monkeypatch.setattr(launch,'start_children',forbidden)
    launch.monitor()


def test_reused_process_identifier_is_never_terminated(tmp_path,monkeypatch):
    monkeypatch.setattr(launch,'ROOT',tmp_path)
    class OtherProcess:
        def create_time(self):return 200
        def terminate(self):raise AssertionError('Attempted to terminate an unrelated process')
    monkeypatch.setattr(launch.psutil,'Process',lambda pid:OtherProcess())
    launch.terminate({'pid':123,'created':100},'tunnel')
