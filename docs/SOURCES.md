<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Fontes oficiais

Mapa público das famílias de dados. Três colunas distintas; não as some nem
as copie uma na outra.

| Coluna | O que mede | Onde conferir |
|---|---|---|
| **Conector** | O que o código *pode* ingerir, a partir de arquivo ou coleta de operador | CLI e [DATA.md](DATA.md) |
| **Esta instalação** | O que *este* clone realmente carregou. Um clone vazio permanece vazio | Sempre `GET /api/coverage` |
| **Última edição certificada** | Recorte imutável já selecionado (release GitHub + JSON de seleção). Não é este clone | [EDUCATION_RELEASE.md](EDUCATION_RELEASE.md), [PUBLIC_DATA_RELEASE.md](PUBLIC_DATA_RELEASE.md), `data/releases/` |

`national_catalog_certified` permanece **sempre** `false`, inclusive depois de
instalar as edições abaixo, de ver 27 UFs ou de processar todas as linhas de um
arquivo. Falhas e cargas parciais continuam visíveis em `GET /api/imports`. A
aplicação começa sem cadastro; não há semente disfarçada de registro oficial.
Nenhum fluxo de lista, busca ou contribuição exige LLM, banco vetorial ou chave
paga de mapa.

## Seis famílias

| Família | Ponto oficial de partida | Conector | Esta instalação | Última edição certificada | Notas de honestidade |
|---|---|---|---|---|---|
| IBGE | [Localidades](https://servicodados.ibge.gov.br/api/docs/localidades) · `GET /api/v1/localidades/municipios` | `bdt import-ibge` | `GET /api/coverage` → `sources.id=ibge` (`municipalities`). Clone vazio: 0 | 5.571 municípios **reutilizados** em `education-2025-20260907-v1` (mesmos bytes compartilháveis com `public-data-20260906-v1`). Não é certificação nacional IBGE autônoma | Snapshot reutilizado não é coleta nova. Código municipal de 6 dígitos só converte com esta tabela carregada |
| Inep | [Microdados do Censo Escolar](https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/censo-escolar) | `bdt import-inep` | `GET /api/coverage` → `sources.id=inep`. Clone vazio: 0 escolas | Tag `education-2025-20260907-v1`: **138.086** escolas públicas ativas no perfil, **0** com geometria (214.192 linhas lidas; 76.106 fora do perfil) | Incidente TLS de 2026-09-06 é histórico; **não desabilitar TLS**. Não são vagas, horários nem qualidade de ensino |
| CNES | [API estabelecimentos](https://apidadosabertos.saude.gov.br/cnes/estabelecimentos) · distribuição CSV do catálogo oficial | `bdt import-cnes` / carga em lote | `GET /api/coverage` → `sources.id=cnes`. Clone vazio: 0 | Tag `public-data-20260906-v1`: **96.123** elegíveis, **7** sem coordenadas, perfil de atendimento **ambulatorial SUS declarado** | A primeira página da API **não** é o Brasil. Gestão municipal ≠ elegibilidade. Não é agenda nem toda a rede SUS |
| PNCP | [Dados abertos PNCP](https://www.gov.br/pncp/pt-br/acesso-a-informacao/copy_of_dados-abertos) · `GET /api/consulta/v1/contratos` | sincronização de recursos / metadados (`bdt sync-resources pncp_contracts`) | `GET /api/coverage` → `sources.id=pncp` (`resources`, não pinos). Clone vazio: 0 | **6.677** contratos da janela de publicação **2026-09-04**, dentro de `public-data-20260906-v1` | Metadado de contrato **não** é pagamento. Município do comprador **não** vira pino de execução. A janela não é o histórico nacional |
| Transferegov | [Download de dados](https://www.gov.br/transferegov/pt-br/ferramentas-gestao/dados-abertos/download-dados) · [API pública](https://api-publica.transferegov.gestao.gov.br/) | `bdt import-transferegov` (CSV + perfil JSON) | `GET /api/coverage` → `sources.id=transferegov`. Clone vazio: 0 | Um **plano de transferência especial** em `public-data-20260906-v1`. Tabela `finance` da edição: **0**. Inspeções CSV podem congelar `records_imported: 0` | Esse freeze **não** é sucesso. Fases (previsão, aditivo, desembolso) **nunca** se somam. Pré-convênio não é instrumento assinado |
| Obrasgov | [API pública](https://api-publica.obrasgov.gestao.gov.br/) · `/obras/projeto-investimento` | importação de projeto (`bdt sync-resources obrasgov_projects`) | `GET /api/coverage` → `sources.id=obrasgov`. Clone vazio: 0 | **Um** projeto em `public-data-20260906-v1` | Endereço do órgão / comprador **não** é o canteiro. `facility_id` exige evidência revisada; o perfil de metadados não inventa vínculo com escola ou UBS |

Somente estas seis famílias são de primeira classe. FNS, CGU e módulos
Transferegov/Obrasgov além dos perfis acima **não** são conectores embarcados
neste catálogo. SICONFI, PDDE e a execução física do Obrasgov têm coletor de
operador fora das famílias (abaixo); não há cobertura fictícia para ninguém.

FNS Fundo a Fundo **ainda não está neste catálogo**: ponto oficial
[portalfns.saude.gov.br/downloads](https://portalfns.saude.gov.br/downloads/),
sem conector, sem SHA/colunas certificados, sem linha em `GET /api/coverage`.
Isso é fonte não ligada (`not_wired`), não “zero repasses”. Licença do portal
CC BY-ND 3.0 **impede ZIP público derivado**. Spike:
[reports/20260909-fns-spike.md](reports/20260909-fns-spike.md).

CGU Portal da Transparência **ainda não está neste catálogo**: o recenseamento,
se existir, é CSV em
[download-de-dados](https://portaldatransparencia.gov.br/download-de-dados)
(convênios, recursos transferidos, emendas) — não a API pontual. Transferências
e convênios usam código **SIAFI**, não IBGE7; emendas têm município IBGE que
pode vir vazio. Bolsa/BPC/servidores nominais permanecem recusados. Sem HOSTS
novo. Spike:
[reports/20260909-cgu-spike.md](reports/20260909-cgu-spike.md).

SICONFI **continua fora das seis famílias**: HTTPS
`apidatalake.tesouro.gov.br` serve RREO/DCA do **ente**, nunca pagamento de
escola. Conjunto sob **ODbL**. O coletor de operador
`python -m bdt.siconfi collect|import` grava `siconfi_reports` com SHA-256,
exercício/período/anexo e vínculo municipal apenas com `cod_ibge` de 7 dígitos;
não infla contagens nem famílias (a tentativa de importação aparece em `runs` e
no agregado `other` de `GET /api/coverage`) e não certifica o país. Spike:
[reports/20260909-siconfi-spike.md](reports/20260909-siconfi-spike.md).

PDDE/FNDE **continua fora das seis famílias**: o PDDE Básico paga UEx/EEx/EM
(CNPJ), não um Place; o arquivo Básico traz `CO_ESCOLA`, não `CO_ENTIDADE`. O
coletor de operador `python -m bdt.pdde collect|import` grava `pdde_payments`
com SHA-256 e encoding registrados e só liga `inep:<CO_ESCOLA>` quando o lugar
já existe no catálogo. Não infla contagens nem famílias; a tentativa de
importação aparece em `runs` e no agregado `other`. Spike:
[reports/20260909-pdde-spike.md](reports/20260909-pdde-spike.md).

**Compras.gov.br.** O endpoint público
`dadosabertos.compras.gov.br/modulo-contratos/1_consultarContratos` é recortado
por órgão (`codigoOrgao`) e janela de vigência inicial de até 365 dias; o
coletor de operador `python -m bdt.compras collect|import` grava
`compras_contracts` com SHA-256 e sem nenhum vínculo territorial (o DTO não
publica IBGE/UF). Contrato publicado não é execução, pagamento nem liquidação;
contratos excluídos pelo publicador ficam com `excluded=True` e payload
original. Licença declarada no site: CC BY-ND 3.0. Não infla contagens nem
famílias; a tentativa aparece em `runs` e no agregado `other`.

**Transferegov Especiais.** O endpoint público
`api-publica.transferegov.gestao.gov.br/especiais/empenhos-especiais` lista
empenhos das transferências especiais; o coletor de operador
`python -m bdt.transferegov_especiais collect|import` grava
`transferegov_especiais_empenhos` com SHA-256 e `id_plano_acao` para junção
futura, e nenhum vínculo municipal (não há código IBGE no payload; UF/CNPJ/nome
existem só no endpoint de beneficiários, fora desta fatia). Empenho não é
desembolso nem pagamento; valores nunca são somados. Não infla contagens nem
famílias.

**FNS Fundo a Fundo.** O portal publica o repasse FAF anual (XLSX em 2026;
CSV em anos anteriores) sob **CC BY-ND 3.0** — dado aberto com atribuição; a
licença restringe distribuir cópias modificadas, não o uso. O coletor
`python -m bdt.fns collect|import` baixa o arquivo original, guarda SHA-256 e
processa localmente; o produto não publica espelho derivado. `CO_MUNICIPIO_IBGE` vem com **6 dígitos** (dígito
verificador suprimido) e o vínculo municipal usa apenas o crosswalk derivado
das identidades IBGE já carregadas — nunca preenchido por nome. `VL_BRUTO`,
`VL_LIQUIDO` e `VL_SALDO_CONTA` ficam como texto exato e nunca são somados.
Não infla contagens nem famílias.

**CGU Recursos transferidos.** O endereço mensal
`.../download-de-dados/transferencias/{YYYYMM}` responde 302 para o CDN
`dadosabertos-download.cgu.gov.br`; o coletor
`python -m bdt.cgu_transferencias collect|import` guarda SHA-256 e a cadeia de
redirect. O CSV é cp1252 com ponto-e-vírgula; `CÓDIGO MUNICÍPIO SIAFI` tem
**4 dígitos** e não existe coluna IBGE — nenhum vínculo municipal é criado.
O recorte não contém pessoa física (censo completo de 2026-09-27); ainda assim
linhas de categoria PF são rejeitadas e contadas por defesa. Sem somas.
Licença: Decreto 8.777 (livre utilização com atribuição); o produto não publica
espelho derivado do dump.

**CGU Emendas parlamentares.** O dump `EmendasParlamentares.zip` (CDN direto)
traz três blocos: por emenda, por convênio e por favorecido; o coletor
`python -m bdt.cgu_emendas collect|import` grava `cgu_emendas` com `block`,
SHA-256 e valores como texto exato (empenhado/liquidado/pago/restos nunca
somados). O bloco por favorecido rejeita e conta pessoa física (≈21,9% do
arquivo em 2026-09-27); `Código Município IBGE` vem com 7 dígitos ou o literal
"Sem informação" e só vincula com chave exata no IBGE carregado. Licença:
Decreto 8.777 com atribuição; sem espelho derivado.

**PNCP atas (operador).** `python -m bdt.pncp_atas collect|import` consulta
`/api/consulta/v1/atas` por janela de **vigência** (≤365 dias), página 10–500 e
filtro opcional por CNPJ do órgão; resultado vazio é HTTP 204. O endpoint não
publica fornecedor, valores nem município/IBGE — nada disso é inventado. O
volume é alto (487 mil atas para um único dia de vigência em 2026-09-27), então
`--max-pages` é obrigatório na prática; `complete` não é cobertura.

**Obrasgov (catálogo).** `python -m bdt.obrasgov_catalog collect|import`
cobre `projeto-investimento`, `geometria`, `empenho` e `contrato` (página ≤200).
Só `geometria` publica `cod_ibge` (7 dígitos, guardado como texto, sem vínculo
criado); `empenho` publica fases (`liquidado`/`pago`/…) que **nunca** se somam;
o CNPJ do fornecedor no contrato vem mascarado e é guardado como publicado.

**Compras.gov.br itens.** `--dataset itens` no mesmo coletor grava
`compras_contract_items` com `numeroControlePncpContrato` como chave de junção
e itens excluídos preservados (`excluded=True`).

## Restante (honestidade)

Caches e CLIs de operador abaixo **não** preenchem a tabela das seis famílias,
**não** ligam FNS/CGU e **não** transformam os coletores
SICONFI/PDDE/execução Obrasgov/Compras/Especiais/FNS/CGU/PNCP
atas/catálogo Obrasgov em famílias; **não** mudam
`national_catalog_certified` (permanece `false`).

**Transferegov financeiro.** ZIPs cacheados em `data/downloads/transferegov/`.
O freeze
[`reports/20260909-transferegov-freeze.json`](reports/20260909-transferegov-freeze.json)
tem `records_imported: 0`: validou bytes, SHA-256, membro ZIP e cabeçalhos;
não persistiu linhas. A ingestão de operador **pode** agora transmitir em
fluxo (stream) todas as linhas dos ZIPs cacheados para um SQLite **novo**
(não `data/bdt.db`):

```bash
python -m ops.transferegov_financial_download_and_ingest --mode ingest \
  --database data/transferegov-finance.db
```

O comando recusa `data/bdt.db`. Se o recibo ainda tiver `limits` diferente de
`null` (tetos em `agreements`/`amendments`/`disbursements`), aquela execução
foi limitada. Uma execução sem teto ainda **nunca** soma fases (previsão,
aditivo, desembolso) e **nunca** define `national_catalog_certified`. Este
freeze/ingest **não** republica a tabela `finance` da edição
`public-data-20260906-v1` (permanece **0**).

**CNEFE 2022.** O cache em `data/cnefe_cache/` tem **27/27** UFs em disco
nesta instalação (onda 2026-09-10). Instantâneo anterior:
[`reports/20260909-cnefe-cache-inventory.md`](reports/20260909-cnefe-cache-inventory.md)
(11 presentes). Restante:
[`reports/20260910-cnefe-remainder.md`](reports/20260910-cnefe-remainder.md).
`ftp.ibge.gov.br` continua **fora** de `HOSTS`; a coleta das 16 UFs que
faltavam usou a exceção de operador `BDT_CNEFE_OPERATOR_DOWNLOAD=1`, **não**
expansão da allowlist. Candidatos de nome (`cnefe_candidate`) ficam inéditos;
**não** são pinos. 27 ZIPs **não** certificam o catálogo nacional.

**Obrasgov.** A amostra limitada de páginas/UFs
(`python ops/ingest_obrasgov_batch.py`) **não** é recenseamento do Brasil.
Um projeto na edição certificada também não o é. O coletor de operador
`python -m bdt.obrasgov_execution collect|import` grava `obrasgov_execution`
com o percentual e as datas declarados por projeto; isso não é pagamento, não
é município e não é censo.

FNS e CGU permanecem `not_wired`: sem conector e sem linha em
`GET /api/coverage`, sem cobertura fictícia. SICONFI, PDDE e a execução física
do Obrasgov têm coletor de operador, continuam fora das seis famílias e não
mudam `national_catalog_certified`.

## Como ler esta instalação

Depois de subir a API local (clone vazio ou banco já importado):

```http
GET /api/coverage
GET /api/imports
```

Você deve ver `"national_catalog_certified": false`. Em clone recém-inicializado,
`summary.places` e `summary.resources` são 0 e cada família aparece com
`data_state: not_loaded` (IBGE só passa a `loaded` se municípios tiverem sido
importados). Uma tentativa falha não apaga totais já gravados e não significa
que o serviço deixou de existir no mundo real.

Instalar uma edição certificada **preenche esta instalação**; não converte o
clone no país inteiro, não atualiza sozinha a fonte e não muda
`national_catalog_certified`. Painel correspondente na interface: cobertura.

## Conectores (o que o código ingere)

Comandos de operador, fora da requisição web. URLs e datas são as da edição
real; não invente competência. Detalhe de campos e falhas: [DATA.md](DATA.md).
Exportar/instalar pacote público: [CATALOG_RELEASES.md](CATALOG_RELEASES.md).

```bash
# IBGE — JSON de localidades
bdt download https://servicodados.ibge.gov.br/api/v1/localidades/municipios data/municipios.json
bdt import-ibge data/municipios.json \
  --url https://servicodados.ibge.gov.br/api/v1/localidades/municipios \
  --reference-date DATA_DA_EDICAO

# Inep — membro CSV escolhido pelo operador (sem extração livre do ZIP)
bdt import-inep data/censo.zip --member CAMINHO_EXATO_DA_TABELA.csv \
  --encoding cp1252 --url URL_OFICIAL_DO_ARQUIVO --reference-date ANO_BASE

# CNES — JSON da API (a primeira página não é carga nacional)
bdt import-cnes data/cnes.json --root estabelecimentos \
  --url URL_OFICIAL_DA_EDICAO --reference-date COMPETENCIA

# Transferegov — CSV com perfil revisado (não é todos os módulos)
bdt import-transferegov data/arquivo.csv --profile data/perfil-revisado.json \
  --url URL_OFICIAL --reference-date DATA_REFERENCIA

# PNCP / plano especial Transferegov / projeto Obrasgov — metadados, não pagamentos
bdt sync-resources pncp_contracts --folder data/collections/pncp-YYYYMMDD \
  --start YYYYMMDD --end YYYYMMDD --collect
bdt sync-resources transferegov_special_plans --folder data/collections/tgov-plano --identity ID
bdt sync-resources obrasgov_projects --folder data/collections/obras-projeto --identity ID
```

Cargas nacionais de operador, quando usadas, também **não** certificam o país:
`python ops/education_bulk.py --year 2025` (Inep) e
`python ops/cnes_quality_catalog.py` (CNES em lote, CSV do catálogo). Obras
conhecidas no formato canônico de lugar entram por `bdt import-places`, com
fonte na CLI; isso não geocodifica a partir do comprador.

Há ainda `bdt import-transferegov-finance` para convênios/aditivos/desembolsos
SICONV. Essa via **não** está na edição `public-data-20260906-v1` (`finance: 0`).
Arquivo CSV em cache com `records_imported: 0` (sondas de índice/CSV) é
congelamento da inspeção, não ingestão.

## Última edição certificada (não este clone)

Seleções versionadas no repositório; os ZIPs vivem nas releases GitHub de
`rafaelob/brasildetodos`. Imutabilidade administrativa do GitHub **não** está
habilitada: a proteção é o hash da seleção, não a promessa de que um asset nunca
seja substituído.

| Tag | Seleção | O que a seleção afirma | O que ela não afirma |
|---|---|---|---|
| `education-2025-20260907-v1` | `data/releases/education-2025-20260907-v1.json` | 138.086 escolas; 0 geometria; 5.571 registros IBGE reutilizados; ZIP 23.807.757 bytes, SHA-256 `483bba3a2e71d5360061cbc1880b41c8ab4915e94199a74bb8ac5678ee5fcfe7` | Nova coleta Inep; vagas; coordenadas inventadas; certificação IBGE autônoma |
| `public-data-20260906-v1` | `data/releases/public-data-20260906-v1.json` | 96.123 lugares CNES (7 sem coordenadas); 6.679 recursos = 6.677 PNCP (04/09/2026) + 1 plano Transferegov + 1 projeto Obrasgov; `finance: 0`; ZIP 28.096.042 bytes, SHA-256 `6d62f9ca107f3672e8dcfb0a7d0b591010931d9daa05eaf6212c91c3cecc1639` | Pagamentos; agenda SUS; canteiro geocodificado; catálogo escolar (essa tag não o contém) |

Conferir bytes **antes** de usar (comandos das páginas de release; não alteram um
banco existente):

```sh
python ops/education_release.py education-catalog.zip \
  --selection data/releases/education-2025-20260907-v1.json
python ops/verify_published_data.py public-data.zip \
  --selection data/releases/public-data-20260906-v1.json
```

Se as **duas** edições forem instaladas juntas, o resultado esperado documentado
é 234.209 lugares (96.123 + 138.086), 6.679 recursos, 5.571 municípios
compartilhados e 138.093 lugares sem coordenadas. Isso continua sem certificação
nacional. Procedimento: [UNIFIED_INSTALLATION.md](UNIFIED_INSTALLATION.md). Não
substitua um banco com usuários.

## Inep e TLS

A descoberta do ZIP 2025 na página oficial funcionou; um download posterior
falhou na verificação de certificado (código 20, emissor RNP ICPEdu). O
incidente de 2026-09-06 permanece no histórico. A tag escolar **não** é esse
download falho: preserva o artefato da coleta `34078768110`. Complementar o
intermediário revisado, se usado, ainda exige cadeia até raiz já distribuída.
Não desabilitar TLS, não usar HTTP, não instalar raiz nova, não trocar de
espelho não verificado.

## O que nenhuma coluna afirma

- Completude do Brasil, atualidade da fonte ou atendimento disponível agora.
- Vínculo escola/UBS/obra por nome, proximidade ou município do comprador.
- Soma entre fases financeiras, fontes ou naturezas (evento / cumulativo / estimativa).
- Licença irrestrita dos dados: a AGPL do código não relicencia IBGE, Inep,
  Ministério da Saúde/CNES, PNCP, Transferegov nem Obrasgov. Ver
  [ATTRIBUTION.md](ATTRIBUTION.md).

## Documentação relacionada

- [DATA.md](DATA.md) — integração file-first, perfis e falhas
- [CATALOG_RELEASES.md](CATALOG_RELEASES.md) — exportar / verificar / instalar tabelas públicas
- [EDUCATION_RELEASE.md](EDUCATION_RELEASE.md) — edição escolar 2025
- [PUBLIC_DATA_RELEASE.md](PUBLIC_DATA_RELEASE.md) — edição CNES + recursos
- [ATTRIBUTION.md](ATTRIBUTION.md) — licenças e atribuição
- [CNES_QUALITY.md](CNES_QUALITY.md) — perfil ambulatorial SUS e quarentena
- [RESOURCE_INGESTION.md](RESOURCE_INGESTION.md) — metadados PNCP / Transferegov / Obrasgov
- [BUNDLE_INSTALLATION.md](BUNDLE_INSTALLATION.md) — instalação atômica da edição de saúde/recursos
