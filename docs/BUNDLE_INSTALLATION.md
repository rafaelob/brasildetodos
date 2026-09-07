<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Instalação atômica do pacote público

A distribuição `public-data-20260906-v1` está em Releases do GitHub. O arquivo
`data/releases/public-data-20260906-v1.json` fixa o hash externo, tamanho,
identificadores e contagens revisados. O arquivo baixado não escolhe o próprio
hash de confiança. A release não tem imutabilidade administrativa habilitada;
a proteção do cliente é a seleção versionada de bytes, não uma promessa de
que um administrador nunca possa substituir um asset.

Com Python 3.14.7 e as dependências travadas instaladas, baixe `public-data.zip`
da release e execute, a partir da raiz do repositório:

```sh
python ops/verify_published_data.py public-data.zip --selection data/releases/public-data-20260906-v1.json
python ops/public_data_bundle.py install public-data.zip --sha256 6d62f9ca107f3672e8dcfb0a7d0b591010931d9daa05eaf6212c91c3cecc1639 --output ./data/application.db
```

A primeira operação reinstala e consulta o conjunto completo em banco temporário.
A segunda cria um banco novo para o operador. Nenhuma delas substitui um banco
existente. Não é necessário extrair o ZIP manualmente. O catálogo e os recursos
são instalados numa área temporária no mesmo sistema de arquivos do destino.
Uma falha de importação, contagem, integridade ou checkpoint descarta essa área;
a publicação final usa uma operação atômica que recusa colisões.

São recusados destinos existentes, links simbólicos e sidecars SQLite `-wal`,
`-shm` e `-journal`. O operador deve reservar uma pasta sem escritores concorrentes
até concluir a instalação e só então iniciar a aplicação. O recibo mostra o hash
do banco antes da primeira inicialização da aplicação, que poderá criar suas
próprias tabelas. Não publica caminhos locais, contas, tokens ou documentos.

Os seis arquivos de OCR e o manifesto estão em `tests/corpus/ocr-reviewed/`.
`python ops/archive_ocr_evidence.py verify tests/corpus/ocr-reviewed` verifica
os bytes e a extração nativa, sem rede nem nova execução de OCR. São documentos
sintéticos identificados; não são convênios oficiais nem entram no pacote público.

O workflow `Published data and OCR acceptance` baixa os bytes efetivamente
publicados, confere a seleção versionada e testa a API em Python 3.14.7. Ele tem
somente permissão de leitura: não cria release, não altera o main e não faz deploy.
O workflow Quality também verifica o corpus versionado em toda execução.
