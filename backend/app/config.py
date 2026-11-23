import os
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_url: str
    demo: bool
    ai_mode: str
    ollama_url: str
    ollama_model: str
    ai_timeout: float
    cookie_secure: bool
    allowed_origins: tuple[str, ...]
    max_upload: int = 10 * 1024 * 1024
    session_hours: int = 12
    remote_demo: bool = False
    public_hostname: str = ''
    access_issuer: str = ''
    access_audience: str = ''
    full_demo: bool = False
    public_demo: bool = False
    public_origin_host: str = ''
    allowed_hosts: tuple[str, ...] = ()
    pages_origin: str = ''

    @classmethod
    def from_env(cls):
        # Parse only AXON_* assignments. Never execute configuration as shell code.
        env_file = ROOT / '.env'
        if os.getenv('AXON_SKIP_DOTENV')!='true' and env_file.is_file():
            for line in env_file.read_text(encoding='utf-8').splitlines():
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    if key.startswith('AXON_') and key.replace('_', '').isalnum():
                        os.environ.setdefault(key, value.strip().strip('"\''))
        data = Path(os.getenv('AXON_DATA_DIR', str(ROOT / 'data'))).resolve()
        mode = os.getenv('AXON_AI_MODE', 'auto')
        if mode not in ('auto', 'ollama', 'simulated'):
            raise ValueError('AXON_AI_MODE debe ser auto, ollama o simulated')
        from urllib.parse import urlsplit
        ollama_url=os.getenv('AXON_OLLAMA_URL','http://127.0.0.1:11434').rstrip('/')
        parsed=urlsplit(ollama_url)
        if parsed.scheme not in ('http','https') or parsed.hostname not in ('localhost','127.0.0.1','::1') or parsed.username or parsed.password:raise ValueError('El modelo de AXON debe usar una dirección local de Ollama')
        default_origins = 'http://127.0.0.1:8000,http://localhost:8000,http://127.0.0.1:5173,http://localhost:5173'
        origins = tuple(value.strip() for value in os.getenv('AXON_ALLOWED_ORIGINS', default_origins).split(',') if value.strip())
        hosts = tuple(value.strip().lower() for value in os.getenv('AXON_ALLOWED_HOSTS', '').split(',') if value.strip())
        secure = os.getenv('AXON_COOKIE_SECURE', 'false').lower() == 'true'
        if any(not re.fullmatch(r'[a-z0-9]+(?:[.-][a-z0-9]+)*', host) for host in hosts):
            raise ValueError('AXON_ALLOWED_HOSTS solo admite nombres exactos, sin esquemas ni comodines')
        if hosts and (not secure or not all(f'https://{host}' in origins for host in hosts)):
            raise ValueError('Cada nombre externo requiere cookies seguras y su origen HTTPS exacto')
        pages_origin = os.getenv('AXON_PAGES_ORIGIN', '').strip()
        if pages_origin and not re.fullmatch(r'https://[a-z0-9]+(?:[.-][a-z0-9]+)+', pages_origin):
            raise ValueError('AXON_PAGES_ORIGIN debe ser un origen HTTPS exacto y sin ruta')
        return cls(data, os.getenv('AXON_DATABASE_URL', f'sqlite:///{data / "axon.sqlite3"}'),
                   os.getenv('AXON_DEMO', 'false').lower() == 'true', mode,
                   ollama_url,
                   os.getenv('AXON_OLLAMA_MODEL', 'llama3.2:3b'),
                   float(os.getenv('AXON_AI_TIMEOUT', '60')),
                   secure,
                   origins,
                   remote_demo=os.getenv('AXON_REMOTE_DEMO','false').lower()=='true',
                   public_hostname=os.getenv('AXON_PUBLIC_HOSTNAME',''),
                   access_issuer=os.getenv('AXON_ACCESS_ISSUER','').rstrip('/'),
                   access_audience=os.getenv('AXON_ACCESS_AUDIENCE',''),
                   full_demo=os.getenv('AXON_FULL_DEMO','false').lower()=='true',
                   public_demo=os.getenv('AXON_PUBLIC_DEMO','false').lower()=='true',
                   public_origin_host=os.getenv('AXON_PUBLIC_ORIGIN_HOST',''),
                   allowed_hosts=hosts, pages_origin=pages_origin)
