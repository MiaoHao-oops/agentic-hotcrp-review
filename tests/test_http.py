from fastapi.testclient import TestClient
from app.main import app

client=TestClient(app)

def test_origin_and_host_rejection():
    assert client.get('/',headers={'host':'attacker.example'}).status_code==400
    assert client.post('/api/conferences',headers={'origin':'https://attacker.example'},json={'name':'OSDI'}).status_code==403
    assert client.get('/',headers={'sec-fetch-site':'cross-site'}).status_code==403


def test_submission_validation():
    assert client.post('/api/conferences',json={'name':'X','reviewers':99}).status_code==422


def test_portal_has_no_external_assets():
    r=client.get('/')
    assert r.status_code==200
    assert 'https://' not in r.text
