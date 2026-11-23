"""Exercise file-based academic import using a generated document and a clean database."""
from dataclasses import replace
from secrets import token_urlsafe

from docx import Document
from fastapi.testclient import TestClient

from app.academic_import import provision_bundle
from app.config import Settings
from app.main import create_app


def test_imported_fictitious_docx_has_provenance_and_is_private(tmp_path):
    document_path = tmp_path / 'reglas-inventadas.docx'
    original = Document()
    original.add_heading('Reglas ficticias 2031–2032', 0)
    original.add_paragraph('Nota de evaluación: Pruebas escritas 65%, actividades 20%, prácticas 15%.')
    original.add_paragraph('Recuperación o mejora')
    table = original.add_table(rows=1, cols=4)
    for cell, value in zip(table.rows[0].cells, ('UD12', 'Circuitos de ejemplo', '1', '5')):
        cell.text = value
    original.save(document_path)
    storage = tmp_path / 'instance'
    settings = replace(Settings.from_env(), data_dir=storage, database_url=f'sqlite:///{storage}/axon.sqlite3',
                       ai_mode='simulated', demo=False)
    app = create_app(settings, maintenance=False)
    with app.state.session_factory() as db:
        result = provision_bundle(db, settings, {
            'username': 'alumno.ejemplo', 'name': 'Titular inventado', 'center': 'Centro de práctica',
            'town': 'Villa Ejemplo', 'academic_year': '2031-2032', 'course': 'Curso de prueba',
            'group': 'Grupo sintético', 'subjects': ['Física y Química'], 'manual': [],
            'documents': [{'path': str(document_path), 'kind': 'physics', 'subject': 'Física y Química',
                           'title': 'Evaluación ficticia', 'academic_year': '2031-2032'}],
        })
    token = (storage / 'private-account-setup.txt').read_text().strip().split('#setup=')[1]
    with TestClient(app) as visitor, TestClient(app) as owner:
        assert visitor.get('/api/public/info').json()['center'] is None
        assert visitor.get('/api/knowledge').status_code == 401
        activated = owner.post('/api/onboarding/finish', json={'token': token, 'password': token_urlsafe()})
        assert activated.status_code == 200
        assert result['user_id'] == activated.json()['user']['id']
        knowledge = owner.get('/api/knowledge').json()
        assert knowledge['policies'][0]['weights'] == {'exams': '65', 'activities': '20', 'practical': '15'}
        assert knowledge['units'][0]['title'] == 'Circuitos de ejemplo'
        assert knowledge['sources'][0]['title'] == 'Evaluación ficticia'
