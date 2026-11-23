"""Startup boundaries: never adopt/kill occupied services or publish without local AI."""
from dataclasses import replace
from pathlib import Path
import pytest
from app import launcher
from app.config import Settings

@pytest.fixture
def prepared(tmp_path,monkeypatch):
    monkeypatch.setattr(launcher,'ROOT',tmp_path)
    interface=tmp_path/'frontend/dist';interface.mkdir(parents=True);(interface/'index.html').write_text('fictitious UI')
    return tmp_path


def test_reuses_healthy_services_without_spawning(monkeypatch):
    monkeypatch.setattr(launcher,'ollama_ready',lambda s:True)
    monkeypatch.setattr(launcher,'private_ready',lambda:True)
    def forbidden(*a,**kw):pytest.fail('Duplicated a running service')
    monkeypatch.setattr(launcher,'spawn',forbidden)
    assert launcher.ensure_ollama(Settings.from_env()) is None
    assert launcher.ensure_private() is None


def test_occupied_unhealthy_port_is_not_replaced(monkeypatch):
    monkeypatch.setattr(launcher,'ollama_ready',lambda s:False)
    monkeypatch.setattr(launcher,'private_ready',lambda:False)
    monkeypatch.setattr(launcher,'busy',lambda *a:True)
    monkeypatch.setattr(launcher,'spawn',lambda *a:pytest.fail('Tried to replace an unrelated process'))
    with pytest.raises(launcher.LaunchError,match='ocupada'):launcher.ensure_ollama(Settings.from_env())
    with pytest.raises(launcher.LaunchError,match='ocupada'):launcher.ensure_private()


def test_new_ollama_binds_only_loopback_and_disables_cloud(monkeypatch):
    settings=replace(Settings.from_env(),ollama_url='http://localhost:11435')
    monkeypatch.setenv('OLLAMA_HOST','0.0.0.0:11434')
    monkeypatch.setattr(launcher,'ollama_ready',lambda s:False)
    monkeypatch.setattr(launcher,'busy',lambda *a:False)
    monkeypatch.setattr(launcher.shutil,'which',lambda name:'/usr/local/bin/ollama')
    captured={}
    def spawn(cmd,env,name):captured.update(command=cmd,env=env,name=name);return object()
    monkeypatch.setattr(launcher,'spawn',spawn);monkeypatch.setattr(launcher,'wait_ready',lambda *a,**kw:None)
    monkeypatch.setattr(launcher.demo_launch,'process_record',lambda p:{'pid':123,'created':100})
    launcher.ensure_ollama(settings)
    assert captured['command']==['/usr/local/bin/ollama','serve']
    assert captured['env']['OLLAMA_HOST']=='127.0.0.1:11435'
    assert captured['env']['OLLAMA_NO_CLOUD']=='1' and captured['env']['OLLAMA_NUM_PARALLEL']=='1'


def test_private_start_cannot_inherit_public_database_or_listen_on_lan(prepared,monkeypatch):
    monkeypatch.setenv('AXON_HOST','0.0.0.0');monkeypatch.setenv('AXON_PUBLIC_DEMO','true');monkeypatch.setenv('AXON_DATA_DIR','/outside/data')
    monkeypatch.setattr(launcher,'private_ready',lambda:False);monkeypatch.setattr(launcher,'busy',lambda *a:False)
    captured={}
    def spawn(cmd,env,name):captured.update(command=cmd,env=env);return object()
    monkeypatch.setattr(launcher,'spawn',spawn);monkeypatch.setattr(launcher,'wait_ready',lambda *a,**kw:None)
    monkeypatch.setattr(launcher.demo_launch,'process_record',lambda p:{'pid':123,'created':100})
    launcher.ensure_private();env=captured['env']
    assert env['AXON_HOST']=='127.0.0.1' and env['AXON_PORT']=='8000'
    assert env['AXON_PUBLIC_DEMO']==env['AXON_REMOTE_DEMO']=='false'
    assert Path(env['AXON_DATA_DIR'])==prepared/'data'
    assert env['AXON_DATABASE_URL']==f'sqlite:///{prepared}/data/axon.sqlite3'


def test_missing_model_does_not_publish_or_download(prepared,monkeypatch):
    monkeypatch.setattr(launcher,'get_json',lambda *a:{'models':[]})
    monkeypatch.setattr(launcher.demo_launch,'start',lambda:pytest.fail('Published without its required model'))
    monkeypatch.setattr(launcher,'spawn',lambda *a:pytest.fail('Started a download or another service'))
    with pytest.raises(launcher.LaunchError,match='modelo'):launcher.start_all()


def test_private_action_never_starts_a_tunnel(prepared,monkeypatch):
    monkeypatch.setattr(launcher,'ensure_ollama',lambda *a:None);monkeypatch.setattr(launcher,'ensure_private',lambda:None)
    monkeypatch.setattr(launcher.demo_launch,'start',lambda:pytest.fail('Private action published a tunnel'))
    assert launcher.start_all(private_only=True)['url']=='http://127.0.0.1:8000'


@pytest.mark.parametrize('url',['http://fixture.trycloudflare.com','https://other.example','https://user:secret@fixture.trycloudflare.com','https://fixture.trycloudflare.com:443'])
def test_never_opens_nonpublic_or_credentialed_urls(url):
    with pytest.raises(launcher.LaunchError,match='HTTPS'):launcher.verify_public(url)


def test_only_verified_current_link_is_written(prepared,monkeypatch):
    monkeypatch.setattr(launcher,'ensure_ollama',lambda *a:None);monkeypatch.setattr(launcher,'ensure_private',lambda:None)
    monkeypatch.setattr(launcher.demo_launch,'start',lambda:{'url':'https://new-fixture.trycloudflare.com','running':True})
    monkeypatch.setattr(launcher,'verify_public',lambda *a:(_ for _ in ()).throw(launcher.LaunchError('Sin respuesta HTTPS')))
    with pytest.raises(launcher.LaunchError):launcher.start_all()
    assert not (prepared/'data/launcher/enlace-publico.txt').exists()


def test_uses_installed_ollama_service_without_empty_user_library(monkeypatch):
    from types import SimpleNamespace
    settings=Settings.from_env();calls=[]
    monkeypatch.setattr(launcher,'ollama_ready',lambda s:False)
    monkeypatch.setattr(launcher,'busy',lambda *a:False)
    monkeypatch.setattr(launcher.shutil,'which',lambda name:'/usr/bin/systemctl' if name=='systemctl' else '/usr/local/bin/ollama')
    def run(cmd,**kw):
        calls.append(cmd)
        if 'show' in cmd:return SimpleNamespace(returncode=0,stdout='not-found' if '--user' in cmd else 'loaded')
        return SimpleNamespace(returncode=0,stdout='')
    monkeypatch.setattr(launcher.subprocess,'run',run)
    monkeypatch.setattr(launcher,'wait_ready',lambda probe,process,*a:None)
    monkeypatch.setattr(launcher,'spawn',lambda *a:pytest.fail('Started an empty per-user model library'))
    result=launcher.ensure_ollama(settings)
    assert result=={'service':'ollama.service','scope':'system'}
    assert ['/usr/bin/systemctl','--no-ask-password','start','ollama.service'] in calls


def test_failed_new_ollama_start_does_not_leave_an_orphan(monkeypatch):
    settings=replace(Settings.from_env(),ollama_url='http://127.0.0.1:11435')
    monkeypatch.setattr(launcher,'ollama_ready',lambda s:False);monkeypatch.setattr(launcher,'busy',lambda *a:False)
    monkeypatch.setattr(launcher.shutil,'which',lambda name:'/usr/local/bin/ollama')
    class Child:
        stopped=False
        def poll(self):return None
        def terminate(self):self.stopped=True
        def wait(self,**kw):return 0
    process=Child();monkeypatch.setattr(launcher,'spawn',lambda *a:process)
    def failed(*a,**kw):raise launcher.LaunchError('No se encuentra el modelo')
    monkeypatch.setattr(launcher,'wait_ready',failed)
    with pytest.raises(launcher.LaunchError):launcher.ensure_ollama(settings)
    assert process.stopped


def test_stop_all_preserves_unknown_private_process(prepared,monkeypatch):
    monkeypatch.setattr(launcher.demo_launch,'stop',lambda:{'running':False})
    monkeypatch.setattr(launcher,'private_ready',lambda:True)
    monkeypatch.setattr(launcher.psutil,'Process',lambda pid:pytest.fail('No tracked process may be adopted'))
    assert launcher.stop_all()['private_running'] is True


def test_stop_all_terminates_only_its_recorded_private_child(prepared,monkeypatch):
    launcher.demo_launch.write(launcher.folder()/'private-process.json',{'pid':123,'created':100})
    monkeypatch.setattr(launcher.demo_launch,'stop',lambda:{'running':False})
    monkeypatch.setattr(launcher,'private_ready',lambda:False)
    class Child:
        stopped=False
        def cmdline(self):return ['python','-m','app.cli','serve']
        def create_time(self):return 100
        def cwd(self):return str(prepared)
        def terminate(self):self.stopped=True
        def wait(self,**kw):return 0
    child=Child();monkeypatch.setattr(launcher.psutil,'Process',lambda pid:child)
    assert not launcher.stop_all()['private_running']
    assert child.stopped
