"""Guided citizen text uses the unchanged authenticated contribution contract."""
from test_api import client, register, login, reviewer, observation, HEAD

TEXT='Registrar visita guiada · bdt.school.field.v1 · pt-BR\nLocal: test:school\nHá identificação visível? Não sei\nContexto: observação sintética para teste.'

def test_guided_text_uses_original_moderated_flow(client,database):
    register(client);login(client)
    submitted=client.post('/api/observations',headers=HEAD,json=observation()|{'body':TEXT,'reference_url':'https://example.org/test-only'})
    assert submitted.status_code==201
    identifier=submitted.json()['id']
    assert submitted.json()['status']=='pending'
    assert client.get('/api/places/test:school').json()['observations']==[]
    assert client.get('/api/observations/mine').json()[0]['observation']['body']==TEXT
    assert TEXT in client.get('/api/account/export').json()['observations'][0]['observation']['body']
    client.post('/api/auth/logout',headers=HEAD);reviewer(database);login(client,'reviewer')
    assert client.post('/api/review/'+identifier,headers=HEAD,json={'decision':'approved','note':'Reviewed the synthetic citizen text.'}).status_code==200
    public=client.get('/api/places/test:school').json()['observations'][0]
    assert public['observation']['body']==TEXT and 'author_id' not in public
    client.post('/api/auth/logout',headers=HEAD);login(client)
    assert client.post('/api/observations/'+identifier+'/withdraw',headers=HEAD).status_code==200
    assert client.get('/api/places/test:school').json()['observations']==[]
