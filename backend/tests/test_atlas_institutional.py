import io
from dataclasses import replace
from sqlalchemy import select
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject,NameObject,NumberObject,DecodedStreamObject
from app.models import User,Document,InstitutionalSource,KnowledgeSource,StudySession
from app.institutional import import_source
from app.documents import retrieve_documents

def pdf(text):
    writer=PdfWriter();page=writer.add_blank_page(width=600,height=800)
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
    stream=DecodedStreamObject();stream.set_data(('BT /F1 14 Tf 40 700 Td ('+text+') Tj ET').encode('ascii'));page[NameObject('/Contents')]=writer._add_object(stream)
    out=io.BytesIO();writer.write(out);return out.getvalue()

def test_institutional_import_dedupe_history_relevance_acl_and_currentness(app,login):
    student=login();admin=login('admin.demo')
    raw=pdf('Proyecto educativo ficticio: prioridad alfabetizacion cientifica y convivencia.')
    with app.state.session_factory() as db:
        user=db.get(User,admin.user['id'])
        first=import_source(db,user,'demo-project',app.state.settings,raw)
        assert first['status']=='imported' and first['applicability']=='unconfirmed'
        assert import_source(db,user,'demo-project',app.state.settings,raw)['status']=='unchanged'
        newer=import_source(db,user,'demo-project',app.state.settings,pdf('Proyecto educativo ficticio: prioridad ciencia abierta y convivencia.'))
        assert newer['version']==2
        fragments=retrieve_documents(db,user,'proyecto educativo ciencia abierta',institutional=True)
        assert fragments and all(f['document_id']==newer['document_id'] for f in fragments)
        assert fragments[0]['institutional']['applicability']=='unconfirmed'
    sources=student.get('/api/atlas/sources').json();assert len(sources)==2
    assert student.post('/api/atlas/institutional/import/demo-project').status_code==403
    assert admin.post('/api/atlas/institutional/import/arbitrary-url').status_code==404
    assert student.get('/api/documents/'+newer['document_id']+'/chunks').status_code==200

def test_tutor_does_not_attribute_latest_unrelated_source(app,login):
    student=login();meta=student.get('/api/academic').json();subject=next(s['id'] for s in meta['subjects'] if s['name']=='Matemáticas')
    with app.state.session_factory() as db:
        source=KnowledgeSource(owner_id=student.user['id'],subject_id=subject,title='Evaluacion de geometria',kind='manual',applicable_year='2026-2027');db.add(source);db.commit()
    r=student.post('/api/study/sessions',json={'subject_id':subject,'topic':'Logaritmos'});assert r.status_code==201,r.text
    assert r.json()['source'] is None and r.json()['topic_alignment']['status']=='no_matching_source'
