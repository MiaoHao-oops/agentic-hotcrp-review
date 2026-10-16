from fastapi.testclient import TestClient
from app.main import app

client=TestClient(app,base_url='http://127.0.0.1',client=('127.0.0.1',50000))

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


def test_untrusted_network_and_spoofed_forwarded_header_rejected():
    outside=TestClient(app,base_url='http://127.0.0.1',client=('192.0.2.10',50000))
    assert outside.get('/',headers={'x-forwarded-for':'127.0.0.1'}).status_code==403


def test_configured_lan_client_allowed(monkeypatch):
    import ipaddress
    from app import main
    monkeypatch.setattr(main,'ALLOWED_NETWORKS',[ipaddress.ip_network('10.156.120.0/24')])
    inside=TestClient(app,base_url='http://127.0.0.1',client=('10.156.120.41',50000))
    assert inside.get('/').status_code==200
    outside=TestClient(app,base_url='http://127.0.0.1',client=('10.156.121.41',50000))
    assert outside.get('/').status_code==403
