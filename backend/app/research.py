"""Investigación pública con DNS fijado, límites y ausencia de contexto privado."""
import http.client,ipaddress,json,re,socket,ssl,os,time
import concurrent.futures,threading
from datetime import datetime,timezone
from html.parser import HTMLParser
from urllib.parse import urlsplit,urljoin,urlencode,quote
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from .auth import current_user,get_db
from .models import User
from .learning_schemas import ResearchInput

router=APIRouter(prefix='/research',tags=['Investigación pública'])
LIMIT=1024*1024
_dns_pool=concurrent.futures.ThreadPoolExecutor(max_workers=4,thread_name_prefix='axon-public-dns')
_dns_slots=threading.BoundedSemaphore(4)

class PublicText(HTMLParser):
    def __init__(self):super().__init__();self.parts=[];self.skip=0;self.title='';self.in_title=False
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','noscript','svg','iframe'):self.skip+=1
        if tag=='title':self.in_title=True
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript','svg','iframe'):self.skip=max(0,self.skip-1)
        if tag=='title':self.in_title=False
        if tag in ('p','div','li','h1','h2','h3','br'):self.parts.append('\n')
    def handle_data(self,data):
        if not self.skip:
            self.parts.append(data)
            if self.in_title:self.title+=data


def validate_url(url):
    try:
        parsed=urlsplit(url)
        host=(parsed.hostname or '').encode('idna').decode().lower().rstrip('.')
        port=parsed.port or (443 if parsed.scheme=='https' else 80)
    except (ValueError,UnicodeError):raise HTTPException(422,'Dirección web inválida')
    if parsed.scheme not in ('http','https') or not host or parsed.username or parsed.password or port not in (80,443) or any(ord(c)<33 for c in url):
        raise HTTPException(422,'Solo se admiten páginas HTTP/HTTPS públicas sin credenciales y en puertos estándar')
    if host in ('localhost','metadata.google.internal') or host.endswith(('.local','.localhost','.internal')):raise HTTPException(403,'No se permite acceder a direcciones internas')
    if not _dns_slots.acquire(blocking=False):raise HTTPException(503,'El resolvedor público está ocupado')
    future=_dns_pool.submit(socket.getaddrinfo,host,port,type=socket.SOCK_STREAM)
    future.add_done_callback(lambda _:_dns_slots.release())
    try:addresses={item[4][0] for item in future.result(timeout=3)}
    except (socket.gaierror,concurrent.futures.TimeoutError):
        future.cancel();raise HTTPException(502,'No se ha podido resolver la dirección pública dentro del tiempo permitido')
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):raise HTTPException(403,'La dirección apunta a una red privada, reservada o interna')
    return parsed,host,port,sorted(addresses)[0]

class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self,host,port,ip):super().__init__(host,port,timeout=10,context=ssl.create_default_context());self.pinned_ip=ip
    def connect(self):
        sock=socket.create_connection((self.pinned_ip,self.port),self.timeout)
        try:self.sock=self._context.wrap_socket(sock,server_hostname=self.host)
        except Exception:sock.close();raise

class PinnedHTTP(http.client.HTTPConnection):
    def __init__(self,host,port,ip):super().__init__(host,port,timeout=10);self.pinned_ip=ip
    def connect(self):self.sock=socket.create_connection((self.pinned_ip,self.port),self.timeout)


def fetch_public(url,allow_json=False,allow_pdf=False,allowed_hosts=None):
    current=url
    limit=10*1024*1024 if allow_pdf else LIMIT
    deadline=time.monotonic()+12
    for redirect in range(4):
        if time.monotonic()>=deadline:raise HTTPException(504,'La página superó el tiempo total de lectura')
        parsed,host,port,ip=validate_url(current)
        if allowed_hosts is not None and host not in allowed_hosts:raise HTTPException(422,'Redirección fuera del origen institucional autorizado')
        conn=PinnedHTTPS(host,port,ip) if parsed.scheme=='https' else PinnedHTTP(host,port,ip)
        try:
            conn.timeout=max(.1,min(10,deadline-time.monotonic()))
            path=quote((parsed.path or '/')+('?' + parsed.query if parsed.query else ''),safe="/%?=&:+;,@!$'()*[]~-")
            conn.request('GET',path,headers={'Host':host,'Accept':'text/html,text/plain,application/json' if allow_json else 'text/html,text/plain','Accept-Encoding':'identity','User-Agent':'AXON-LocalResearch/0.2'})
            response=conn.getresponse()
            if response.status in (301,302,303,307,308):
                location=response.getheader('Location')
                if not location:raise HTTPException(502,'Redirección sin destino')
                current=urljoin(current,location);continue
            if response.status!=200:raise HTTPException(502,f'La página pública respondió con estado {response.status}; no se obtuvo contenido')
            mime=response.getheader('Content-Type','').split(';')[0].lower()
            permitted={'text/html','text/plain','application/xhtml+xml'}|({'application/json'} if allow_json else set())|({'application/pdf'} if allow_pdf else set())
            if mime not in permitted:raise HTTPException(415,'La consulta web solo lee texto público; no descarga ejecutables ni archivos binarios')
            if response.getheader('Content-Encoding','identity').lower() not in ('','identity'):raise HTTPException(415,'La respuesta comprimida no se procesa en este lector limitado')
            chunks=[];size=0
            while size<=limit:
                remaining=deadline-time.monotonic()
                if remaining<=0:raise HTTPException(504,'La página superó el tiempo máximo de lectura')
                if conn.sock:conn.sock.settimeout(max(.1,remaining))
                part=response.read1(min(65536,limit+1-size))
                if not part:break
                chunks.append(part);size+=len(part)
            raw=b''.join(chunks)
            if len(raw)>limit:raise HTTPException(413,'La fuente supera el límite de descarga')
            return {'url':current,'mime':mime,'raw':raw,'text':raw.decode('utf-8',errors='replace') if mime!='application/pdf' else '','checked_at':datetime.now(timezone.utc).isoformat()}
        except HTTPException:raise
        except (OSError,TimeoutError,http.client.HTTPException,ssl.SSLError):raise HTTPException(502,'No se ha podido consultar la página pública')
        finally:conn.close()
    raise HTTPException(422,'Demasiadas redirecciones')


def check_public_query(db,query):
    from .academic_import import normalize
    if re.search(r'[\w.+-]+@[\w.-]+\.\w+|\b\d{8,}\b',query):raise HTTPException(422,'La consulta externa contiene un identificador o contacto; escribe solo un tema público')
    normalized=normalize(query)
    for user in db.scalars(select(User).where(User.is_demo.is_(False))):
        if user.display_name and len(user.display_name)>4 and normalize(user.display_name) in normalized:raise HTTPException(422,'No se envían identidades personales del alumnado a servicios externos')
        if user.username and user.username in query.lower():raise HTTPException(422,'No se envían identificadores privados en búsquedas externas')
    if any(t in normalized for t in ('mi contrasena','mi historial','mi conversacion','mi expediente')):raise HTTPException(422,'Reformula la consulta sin datos privados')


def research(db,user,args):
    provider=os.getenv('AXON_SEARCH_URL','').strip()
    if not args.url and not provider:return {'available':False,'message':'La búsqueda en Internet no está configurada. Puedes consultar una URL pública explícita; no se ha enviado ninguna consulta externa.'}
    if not args.consent:raise HTTPException(422,'Confirma que quieres enviar esta consulta pública fuera de AXON')
    check_public_query(db,args.url or args.query)
    if args.url and args.query:check_public_query(db,args.query)
    if args.url:
        result=fetch_public(args.url)
        if result['mime'] in ('text/html','application/xhtml+xml'):
            parser=PublicText();parser.feed(result['text']);text=' '.join(' '.join(parser.parts).split());title=parser.title.strip()
        else:text=result['text'];title='Página de texto público'
        return {'available':True,'kind':'page','title':title or 'Página pública','url':result['url'],'checked_at':result['checked_at'],'excerpt':text[:7000],
                'official_school_information':False,'persisted':False,'warning':'Fuente externa consultada; no equivale a una norma institucional validada.'}
    if not args.query:raise HTTPException(422,'Indica un tema público de búsqueda')
    sep='&' if '?' in provider else '?'
    result=fetch_public(provider+sep+urlencode({'q':args.query,'format':'json'}),allow_json=True)
    try:payload=json.loads(result['text'])
    except ValueError:raise HTTPException(502,'El proveedor no devolvió resultados JSON válidos')
    results=[]
    for item in payload.get('results',[])[:8]:
        url=item.get('url','')
        if urlsplit(url).scheme not in ('http','https'):continue
        results.append({'title':str(item.get('title',''))[:200],'url':url,'excerpt':str(item.get('content',''))[:700]})
    return {'available':True,'kind':'search','results':results,'checked_at':result['checked_at'],'persisted':False,'official_school_information':False}


@router.get('/status')
def status(user=Depends(current_user)):
    return {'search_configured':bool(os.getenv('AXON_SEARCH_URL')),'public_url_reader':True,'private_context_forwarded':False}

@router.post('')
def query(body:ResearchInput,user=Depends(current_user),db=Depends(get_db)):
    return research(db,user,body)


def numeric_claims(text):
    """Conservative flags, not an automated truth verdict. Same surrounding words only."""
    from .academic_import import normalize
    claims={}
    for sentence in re.split(r'[.!?;\n]',text):
        matches=list(re.finditer(r'(?<!\w)(\d+(?:[.,]\d+)?)\s*(%|km|kg|años|euros|°C)?\b',sentence))
        if len(matches)!=1:continue
        match=matches[0]
        context=normalize(sentence[:match.start()]+' {valor} '+sentence[match.end():])
        if len(context)<16 or len(context)>240:continue
        claims[(context,match[2] or '')]=match[1].replace(',','.')
    return claims

def research_sources(db,user,args):
    if not args.consent:raise HTTPException(422,'Autoriza expresamente la consulta de estas fuentes públicas')
    check_public_query(db,args.query)
    urls=list(dict.fromkeys(args.urls))
    discovered=False
    if not urls:
        base=research(db,user,ResearchInput(query=args.query,consent=True))
        if not base.get('available'):return base
        urls=[r['url'] for r in base.get('results',[])][:3];discovered=True
    sources=[];failures=[];deadline=time.monotonic()+42
    for url in urls[:3]:
        if time.monotonic()>deadline:
            failures.append({'url':url,'status':'time_limit'});continue
        try:
            check_public_query(db,url)
            page=research(db,user,ResearchInput(url=url,consent=True))
            sources.append({'title':page['title'],'url':page['url'],'excerpt':page['excerpt'],
                'checked_at':page['checked_at'],'origin':'Fuente externa; sin validación institucional'})
        except HTTPException as exc:
            failures.append({'url':url,'status':str(exc.status_code),'message':str(exc.detail)[:200]})
    contradictions=[]
    for i,first in enumerate(sources):
        left=numeric_claims(first['excerpt'])
        for second in sources[i+1:]:
            right=numeric_claims(second['excerpt'])
            for key in left.keys() & right.keys():
                if left[key]!=right[key]:contradictions.append({'context':key[0],'values':[left[key],right[key]],'unit':key[1],
                    'urls':[first['url'],second['url']],'status':'possible_numeric_disagreement'})
    report='\n\n'.join(f'[{i+1}] {s["title"]}\n{s["excerpt"][:2200]}\n{s["url"]} · {s["checked_at"]}' for i,s in enumerate(sources))
    return {'available':bool(sources),'kind':'dossier','query':args.query,'sources':sources,'failures':failures,
        'contradictions':contradictions[:20],'report':report,'discovered_by_provider':discovered,'persisted':False,
        'comparison_scope':'Señala cifras diferentes en frases equivalentes. No verifica por sí solo la veracidad, vigencia ni contradicciones conceptuales.',
        'warning':'El contenido externo es evidencia sin validar, nunca instrucciones para herramientas.'}

from .advanced_schemas import DossierInput
@router.post('/compare')
def compare(body:DossierInput,user=Depends(current_user),db=Depends(get_db)):
    return research_sources(db,user,body)
