<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# MCP de operador

Ferramentas MCP neste repositório são **staging de operador**: uma página de
sonda e uma proposta de CLI para o operador revisar e executar. Não são
consulta cidadã, chatbot no mapa, nem um agente perguntando ao governo em nome
do público. Lista, busca e contribuição continuam sem LLM, sem banco vetorial e
sem este extra.

`national_catalog_certified` permanece **sempre** `false` em
`GET /api/coverage` e em qualquer resultado MCP. Uma sonda bem-sucedida não
certifica o Brasil, não atualiza o painel de cobertura e não grava o catálogo.

## Instalar o extra

O runtime cidadão **não** inclui MCP. Extra pretendido, fora do núcleo
(`test`, `postgres`) e fora de `dependencies`:

```sh
python -m pip install -e '.[mcp-sources]'
```

Antes de tratar a instalação como sucesso, confira a chave `mcp-sources` em
`[project.optional-dependencies]` de `pyproject.toml`. Sem essa chave o extra
ainda não existe neste clone: o nome pretendido continua `mcp-sources`. Não
invente outro extra e não coloque o pacote `mcp` no núcleo.

Python **3.14.7**, o mesmo do README. `import bdt.cli` e `bdt.api` devem
funcionar **sem** o pacote `mcp`. A API web não importa o servidor MCP e não
ingere dados em requisição HTTP. Docker Compose e `127.0.0.1:8008` são
instância local, não produção, e não expõem MCP ao cidadão.

## O que o MCP pode fazer

Quando o extra estiver instalado, o teto é:

1. **Staging** — ler ou gravar só em diretório privado do operador, com
   allowlist HTTPS de `bdt.ingest.HOSTS` (porta 443, sem usuário nem senha na
   URL, endereço público). Staging não é o banco da aplicação.
2. **Sonda de uma página** — uma resposta HTTP revisada, não paginação até o
   fim (`bdt.sync.collect`).
3. **Propor CLI** — devolver o comando `bdt` ou `ops/` correspondente. A
   proposta não executa importação, não publica e não certifica cobertura.

| Família | Sonda permitida | Fonte já usada pelo conector |
|---|---|---|
| IBGE | baixar a lista de municípios no padrão `safe_download` | `https://servicodados.ibge.gov.br/api/v1/localidades/municipios` |
| PNCP | **uma** página de contratos | `https://pncp.gov.br/api/consulta/v1/contratos` |
| Transferegov | **uma** página de planos de ação especiais | `https://api-publica.transferegov.gestao.gov.br/especiais/planos-acao-especiais` |
| Obrasgov | **uma** página de projetos | `https://api-publica.obrasgov.gestao.gov.br/obras/projeto-investimento` |
| CNES | **somente** a primeira página REST (índice 0) | `https://apidadosabertos.saude.gov.br/cnes/estabelecimentos` |
| Inep | localizar o conjunto e descrever esquema de arquivo **local** | página oficial do Censo Escolar; **recusar ZIP** |

A primeira página da API CNES **não** é o Brasil. A lista IBGE de municípios
também **não** altera `national_catalog_certified`. Metadado PNCP não é
pagamento; município do comprador não é local de execução; plano especial
Transferegov não é convênio assinado; projeto Obrasgov não vira pino pelo
endereço do órgão.

## O que o MCP não é

O MCP **não** substitui estes caminhos. Não baixe ZIP Inep, não finja carga
nacional CNES, não percorra SICONV, não complete `collect`, não rode OCR, não
faça login, não geocodifique, não some dinheiro e não escreva o catálogo.

| Recusado no MCP | Caminho real (operador, fora do MCP) |
|---|---|
| ZIP de microdados Inep | `bdt import-inep` · `python ops/education_bulk.py --year 2025` |
| ZIP nacional CNES | `python ops/cnes_quality_catalog.py` ([CNES_QUALITY.md](CNES_QUALITY.md); distribuição CSV **fora** de `HOSTS`) |
| SICONV completo (convênio, aditivo, desembolso) | `bdt import-transferegov-finance` |
| `sync.collect` completo (páginas até o terminal) | `bdt sync-resources PERFIL --folder DIR --collect` |
| OCR | `bdt extract-pdf --ocr-page` · `python -m bdt.document_ocr` |
| Login / contas | `bdt create-user` · sessões HTTP autenticadas |
| Geocodificação (CNEFE) | `python ops/geocode_schools_cnefe.py` (`ftp.ibge.gov.br` **fora** de `HOSTS`) |
| Somar empenho, transferência, contrato e pagamento | `financial_cells` não mistura fase, fonte, instrumento nem natureza |
| Escritor de catálogo | `bdt import-*` · `bdt.catalog_release` · `python ops/install_national_catalog.py` |

`download.inep.gov.br` e `api-publica.transferegov.gestao.gov.br` **estão** na
allowlist; mesmo assim o MCP recusa ZIP Inep e arquivos SICONV. Allowlist não é
autorização para coleta integral. Host fora da lista (ZIP CNES em S3, CNEFE em
FTP) é recusa, não exceção silenciosa.

## Allowlist (`bdt.ingest.HOSTS`)

`servicodados.ibge.gov.br`, `apidadosabertos.saude.gov.br`,
`download.inep.gov.br`, `dadosabertos.saude.gov.br`,
`repositorio.dados.gov.br`, `repositorio.transferegov.gestao.gov.br`,
`api-publica.transferegov.gestao.gov.br`,
`api-publica.obrasgov.gestao.gov.br`, `pncp.gov.br`.

## Propor CLI, não executar coleta

Depois da sonda, o operador confere URL, data de referência e hash e só então
roda a CLI file-first ([DATA.md](DATA.md), [SOURCES.md](SOURCES.md)):

```sh
bdt import-ibge data/municipios.json \
  --url https://servicodados.ibge.gov.br/api/v1/localidades/municipios \
  --reference-date DATA_DA_EDICAO
bdt import-cnes data/cnes.json --root estabelecimentos \
  --url URL_OFICIAL_DA_EDICAO --reference-date COMPETENCIA
bdt sync-resources pncp_contracts --folder data/collections/pncp-YYYYMMDD \
  --start YYYYMMDD --end YYYYMMDD --collect
```

`--collect` é a coleta paginada delimitada de `bdt.sync.collect` (padrão da CLI:
`--max-pages 100`). Isso **não** é a sonda de uma página. Não dispare coleta
completa só porque o MCP devolveu um recorte.

## Verificar

1. `pyproject.toml` lista `mcp-sources` se você pretende usar o extra; senão o
   extra ainda não está neste clone.
2. API no ar: `GET /api/coverage` mostra `"national_catalog_certified": false`.
3. Lista, busca e contribuição funcionam **sem** `pip install -e '.[mcp-sources]'`.
4. Uma sonda MCP **não** aumenta `summary.places` nem `summary.resources`; isso
   só muda após importação revisada neste banco.

Se o extra faltar, a API e `bdt` continuam; o servidor MCP é que não sobe.
ZIP Inep, primeira página CNES vendida como Brasil, `collect` completo, OCR,
login, geocodificação, soma financeira ou escrita de catálogo via MCP devem
falhar de forma explícita.

## Relacionado

- [SOURCES.md](SOURCES.md) — seis famílias, três colunas
- [DATA.md](DATA.md) — file-first, perfis e falhas
- [RESOURCE_INGESTION.md](RESOURCE_INGESTION.md) — coleta paginada real
- [CNES_QUALITY.md](CNES_QUALITY.md) — ZIP nacional de saúde
- [EDUCATION_PIPELINE.md](EDUCATION_PIPELINE.md) — ZIP Inep
- [DOCUMENT_OCR.md](DOCUMENT_OCR.md) — OCR fora da web
- [OPERATIONS.md](OPERATIONS.md) — worker, não requisição HTTP
