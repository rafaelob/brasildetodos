<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Preparação de fotografias: componente disponível e integração pendente

O processamento local está implementado em `bdt.photos` e `ops/prepare_photo.py`.
Ele valida bytes JPEG/PNG, limita arquivo/pixels, corrige orientação, aplica máscaras
opacas explícitas e grava um novo derivado JPEG sem repassar EXIF, XMP ou comentários.
Não armazena o original, não associa automaticamente a lugar/observação e não publica.

```sh
python ops/prepare_photo.py fachada.png --output derivado.jpg --masks mascaras.json
```

O arquivo de máscaras é uma lista JSON de até 20 retângulos normalizados, por exemplo:

```json
[{"x":0.25,"y":0.25,"width":0.5,"height":0.5}]
```

Entrada: até 2 MiB e 12 milhões de pixels; JPEG/PNG de pelo menos 16 pixels em
cada dimensão. Derivado: até 2.048 pixels no maior lado e 2 MiB. Não há detecção
automática de rosto, garantia de anonimização ou validação da informação fotografada.
O operador deve examinar o derivado completo. Prefira fachadas e não capture menores,
pacientes, interiores sem autorização ou dados pessoais identificáveis.

A saída só é criada em caminho inexistente, com publicação sem sobrescrita.
O original permanece inalterado. O recibo contém tamanho, dimensões e hash do
**derivado**, não caminho do arquivo, identificação de cidadão ou inferência de GPS.

## Integração HTTP e revisão

O upload fica desligado por padrão (`BDT_PHOTO_UPLOADS=1` habilita). Quando
habilitado, a rota autenticada `POST /api/photos` aceita imagem JPEG/PNG e cria
um derivado privado; o autor vê metadados/imagem em `/api/photos/{id}` e
`/api/photos/{id}/image`. Um revisor diferente do autor aprova ou rejeita em
`POST /api/photos/{id}/review`, com conferência de privacidade explícita.

`GET /api/public/photos/{id}/image` só serve foto aprovada cuja observação
também esteja publicada. A retirada da observação, a retratação da foto e a
desativação da conta removem bytes e metadados pela mesma transação. O export
da conta inclui os próprios metadados, nunca bytes de outra pessoa.

Fotos aprovadas de uma observação compartilhada também podem ser lidas por
membros do grupo em `/api/groups/{group}/tasks/{task}/photos/{photo}/image`,
sem torná-las públicas. A rota exige membro ativo, vínculo com a tarefa e foto
aprovada; retirada/retratação/expulsão encerram o acesso. O consentimento
`share_with_group` cobre a observação e suas fotos aprovadas. Detalhes em
[Grupos](GROUPS.md).

## Testes e evidência

`test_photos.py` usa imagens reais geradas exclusivamente para testes: formato,
orientação, remoção de metadados, máscaras, limites, corrupção e validação de contratos.
`test_prepare_photo.py` exercita os arquivos, falhas e corrida de destino do CLI.
A aprovação em runtimes-alvo é conferida na CI, separada dos testes auxiliares.

Este componente não substitui o corpus de OCR, não fornece panorama e não
encerra a política de retenção, moderação operacional ou licenciamento de
imagens de terceiros.
