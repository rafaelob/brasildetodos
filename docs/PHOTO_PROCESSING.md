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

## O que não foi integrado

A escrita do arquivo central `backend/bdt/api.py` com a integração fotográfica foi
bloqueada pela verificação de segurança da plataforma nesta execução. A alteração
não foi reenviada por outra ferramenta, formato ou mecanismo. O frontend preparado,
as rotas e os hooks de retirada não são apresentados como recurso disponível.
A configuração pública existente mantém `photo_uploads=false`; não há botão novo
que prometa um upload inexistente.

O módulo inclui os modelos e operações transacionais preparados para o fluxo futuro,
mas essas operações não representam uma rota HTTP instalada. A integração completa
continua aberta: envio autenticado, revisão independente, remoção em retirada da
observação/conta, interface nos três idiomas e aceite do navegador. O código do
processador e seu CLI são utilizáveis independentemente dessa integração.

## Testes e evidência

`test_photos.py` usa imagens reais geradas exclusivamente para testes: formato,
orientação, remoção de metadados, máscaras, limites, corrupção e validação de contratos.
`test_prepare_photo.py` exercita os arquivos, falhas e corrida de destino do CLI.
A aprovação em runtimes-alvo é conferida na CI, separada dos testes auxiliares.

Este componente não substitui o corpus de OCR, não fornece panorama e não encerra
a tarefa de fotografias cidadãs do produto completo.
