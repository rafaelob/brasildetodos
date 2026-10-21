<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Integridade da coleta paginada — Issue #2

O coletor confere o arquivo local antes de calcular seu hash: recusa links
simbólicos, arquivos não regulares e páginas acima de `max_bytes_per_page`,
tanto na coleta nova quanto na retomada. Um caminho que já seja um link não é
entregue ao downloader. Isso evita confiar apenas no limite solicitado ao loader.

O número da página e o status HTTP precisam ser inteiros, sem aceitar booleanos
ou floats por igualdade numérica. Páginas com mais registros que `page_size`
falham explicitamente; aumentar esse orçamento exige um perfil revisado. A
revalidação pré-importação repete os limites de registros e o tipo de página.
Uma página curta continua sem provar completude.

Falhas deixam `collection.json` como `failed`; nenhuma dessas validações altera
`national_catalog_certified`, que permanece falso. Os casos são sintéticos e
locais, sem coleta de dados oficiais ou alteração de catálogos publicados.

Regressões: `backend/tests/test_sync_bounds.py`. Foram reproduzidos dez casos de
falha na revisão-base `f95c43955d95b2bf800535729f9b5f8099f4bd5b`.
Comando: `python -m pytest backend/tests/test_sync.py backend/tests/test_sync_bounds.py backend/tests/test_no_content.py`.

Continuam fora deste recorte os denominadores oficiais, a reconciliação nacional
por partição e as garantias de transporte externo. Diretório de staging deve
permanecer restrito ao operador; os checks não são isolamento contra outro
processo com permissão para substituir arquivos durante a leitura.
