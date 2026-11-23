"""Original demonstration documents with explicit provenance and version history."""
from datetime import date
from hashlib import sha256
import threading

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from .auth import current_user, get_db
from .models import Document, DocumentChunk, InstitutionalSource
from .policy import audit, require_role

router = APIRouter(prefix='/atlas/institutional', tags=['Fuentes de demostración'])
CURATED = {
    'demo-project': {
        'title': 'Proyecto educativo de Nébula · simulación', 'category': 'educational_project',
        'text': 'Centro Educativo Nébula, Villa Prisma, territorio ficticio. Código DEMO-001. '
                'El aprendizaje se organiza mediante preguntas, investigación y revisión del trabajo. '
                'El alumnado conserva su privacidad y el profesorado valida las actividades y las correcciones. '
                'Este documento original es una simulación educativa creada para AXON.',
    },
    'demo-rules': {
        'title': 'Convivencia y organización · simulación', 'category': 'school_rules',
        'text': 'Las personas del Centro Educativo Nébula escuchan, respetan turnos y cuidan sus materiales. '
                'El tablón de cada clase reúne avisos y sus comentarios se abren por decisión docente. '
                'Las solicitudes de matrícula se revisan por el equipo autorizado. '
                'Secretaría y jefatura de estudios son puestos ficticios del escenario.',
    },
    'demo-calendar': {
        'title': 'Calendario de Nébula · simulación', 'category': 'school_calendar',
        'text': 'Calendario artificial del Centro Educativo Nébula. Las clases se distribuyen de lunes a viernes. '
                'Hay seis sesiones de 50 minutos y un recreo de 30 minutos tras la tercera sesión. '
                'Las fechas vigentes de exámenes, entregas y evaluaciones se consultan en Calendario. '
                'Las tres evaluaciones son periodos de demostración configurables.',
    },
    'demo-assessment': {
        'title': 'Guía de evaluación · simulación', 'category': 'assessment',
        'text': 'La evaluación ficticia de Nébula combina actividades 30 %, exámenes 35 %, '
                'proyectos 25 % y participación 10 %. Estos pesos son ejemplos configurables. '
                'Las rúbricas describen comprensión, procedimiento y comunicación. '
                'Las calificaciones las devuelve una persona docente autorizada. La IA prepara propuestas para su revisión.',
    },
    'demo-office': {
        'title': 'Guía de secretaría y departamentos · simulación', 'category': 'administration',
        'text': 'Nora Quásar ocupa la dirección ficticia. El coordinador Ivo Lumen organiza las tutorías '
                'y Lyra Nimbo coordina el departamento de comunicación. El equipo de secretaría gestiona '
                'las matrículas de ejemplo. Cada grupo tiene un tutor y un aula asignada. '
                'La demostración incluye ESO, Bachillerato y Formación Profesional con materias de ejemplo.',
    },
}
for key, entry in CURATED.items():
    entry.update(url=f'https://demo.axon.invalid/documents/{key}', academic_year='simulado',
                 applicability='unconfirmed', notes='Documento original ficticio de AXON. Contenido de demostración.')

_capacity = threading.BoundedSemaphore(1)


def import_source(db, user, key, settings, raw=None):
    require_role(user, 'admin')
    if key not in CURATED:
        raise HTTPException(404, 'Documento fuera del catálogo ficticio')
    if not _capacity.acquire(blocking=False):
        raise HTTPException(429, 'Hay otra carga de documentos en curso')
    try:
        entry = CURATED[key]
        if raw is None:
            raw = entry['text'].encode('utf-8')
            suffix = '.txt'
            chunks = [('Documento ficticio · fragmento 1', entry['text'])]
        else:
            from .documents import extract
            if len(raw) > settings.max_upload or not raw.startswith(b'%PDF-'):
                raise HTTPException(415, 'El archivo de demostración debe ser un PDF válido')
            suffix = '.pdf'
            chunks = extract(raw, suffix)
        checksum = sha256(raw).hexdigest()
        prior = db.scalar(select(Document).join(InstitutionalSource).where(
            InstitutionalSource.center_id == user.center_id,
            InstitutionalSource.source_url == entry['url'],
        ).order_by(Document.version.desc()).limit(1))
        if prior and prior.checksum == checksum:
            return {'status': 'unchanged', 'document_id': prior.id, 'version': prior.version}
        from .operations import storage_lock
        with storage_lock(settings):
            path = settings.data_dir / 'uploads' / ('fictional-' + checksum + suffix)
            created = not path.exists()
            if created:
                path.write_bytes(raw)
                path.chmod(0o600)
            try:
                doc = Document(center_id=user.center_id, owner_id=user.id, title=entry['title'],
                               filename=key + suffix, storage_key=path.name, checksum=checksum, access='center',
                               status='validated', source='Original ficticio de AXON', size=len(raw),
                               version=prior.version + 1 if prior else 1)
                db.add(doc)
                db.flush()
                db.add_all(DocumentChunk(document_id=doc.id, ordinal=i, location=location, content=text)
                           for i, (location, text) in enumerate(chunks))
                db.add(InstitutionalSource(center_id=user.center_id, document_id=doc.id,
                    source_url=entry['url'], category=entry['category'], checked_on=date.today().isoformat(),
                    academic_year=entry['academic_year'], verification='fictional_original',
                    applicability=entry['applicability'], authority='fictional', notes=entry['notes']))
                audit(db, user, 'fictional_source_loaded', doc)
                db.commit()
            except BaseException:
                if created:
                    path.unlink(missing_ok=True)
                raise
        return {'status': 'imported', 'document_id': doc.id, 'version': doc.version,
                'chunks': len(chunks), 'applicability': entry['applicability']}
    finally:
        _capacity.release()


@router.get('/catalog')
def catalog(user=Depends(current_user)):
    return [{'key': key, **{k: value for k, value in entry.items() if k != 'text'}}
            for key, entry in CURATED.items()]


@router.post('/import/{key}')
def import_curated(key: str, request: Request, user=Depends(current_user), db=Depends(get_db)):
    return import_source(db, user, key, request.app.state.settings)
