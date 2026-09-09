<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Spike — SICONFI (RREO / DCA; sem importador)

Data da inspeção: **2026-09-09**. Sem censo paginado do datalake ao vivo
(nenhum GET do envelope JSON; só HEAD nos endpoints de dados). Sem
alteração de `HOSTS`. Sem conector.

## Conclusão

**Adiar inclusão pública e operador.** HTTPS no hospedeiro
`apidatalake.tesouro.gov.br` **existe** (HTTP 307 → HTTPS 200; HSTS).
Isso **não** basta para ligar: a chave de junção **não** está
especificada como IBGE7 exclusivo, e a licença do *conjunto de dados*
no catálogo federal é **ODbL** (share-alike), distinta do Apache 2.0
do YAML da API. Default deste spike: adiar a menos que HTTPS + junção
IBGE7 + licença estejam verificados; os três não estão simultaneamente
verificados para um ZIP público derivado.

Ausência no catálogo é **`not_wired`**, não “zero contas municipais
brasileiras”. `GET /api/coverage` não tem família `siconfi`; isso não
mede o SICONFI real. RREO/DCA são contexto fiscal do **ente**, nunca
pagamento de escola ou UBS. `facility_id` não se inventa.

Este spike **não** acrescenta `apidatalake.tesouro.gov.br` a
`backend/bdt/ingest.py` `HOSTS`.

## URLs abertas (status, HTTPS)

Medição local `curl.exe` HEAD, 2026-09-09, sem seguir redirecionamento
salvo onde indicado. Corpos JSON da API **não** foram baixados.

| URL | Método | Status | HTTPS |
|---|---|---|---|
| `http://apidatalake.tesouro.gov.br/docs/siconfi/` | HEAD | **307** `Location: https://apidatalake.tesouro.gov.br/docs/siconfi/` | redireciona |
| `https://apidatalake.tesouro.gov.br/docs/siconfi/` | HEAD | **200** `text/html`; `Last-Modified: Wed, 24 Jun 2026 14:31:16 GMT`; HSTS `max-age=10886400; includeSubDomains; preload` | sim |
| `https://apidatalake.tesouro.gov.br/` | HEAD | **200** | sim |
| `https://apidatalake.tesouro.gov.br/docs/siconfi.yaml` | HEAD | **200** `application/octet-stream`; 44 465 bytes; mesmo `Last-Modified` | sim |
| `https://apidatalake.tesouro.gov.br/ords/siconfi/tt/` | HEAD | **200** corpo vazio | sim |
| `https://apidatalake.tesouro.gov.br/ords/siconfi/tt/entes` | HEAD | **200** `application/json`; HSTS `max-age=31536000;includeSubDomains` | sim |
| `https://apidatalake.tesouro.gov.br/ords/cdwhprd/siconfi/tt/` | HEAD | **200** corpo vazio | sim |
| `https://apidatalake.tesouro.gov.br/ords/cdwhprd/siconfi/tt/entes` | HEAD | **200** `application/json`; **mesmo ETag** que `/ords/siconfi/tt/entes` | sim |
| `http://apidatalake.tesouro.gov.br/ords/siconfi/tt/entes` | HEAD | **307** → `https://apidatalake.tesouro.gov.br/ords/siconfi/tt/entes` | redireciona |
| `https://www.tesourotransparente.gov.br/consultas/consultas-siconfi/siconfi-api-de-dados-abertos` | HEAD | **200** | sim |
| `https://dados.gov.br/dados/conjuntos-dados/api-rreo-entes` | HEAD | **200** | sim |
| `https://dados.gov.br/dados/conjuntos-dados/api-dca-entes` | HEAD | **200** | sim |
| `https://dados.gov.br/dados/conjuntos-dados/api-rgf-entes` | scrape | **200** (corpo) | sim |
| `https://dados.gov.br/dados/conjuntos-dados/api-tabela-entes` | HEAD | **200** | sim |
| `https://www.gov.br/conecta/catalogo/apis/siconfi-extratos-das-declaracoes-contabeis/` | scrape | **200** | sim |
| `http://www.apache.org/licenses/LICENSE-2.0.html` (via YAML) / `https://www.apache.org/licenses/LICENSE-2.0.html` | HEAD | **200** | sim (HTTPS) |

O downloader do produto (`safe_download`) só aceita `https` + hostname
na allowlist + porta 443. O hostname candidato, **se** um dia o OWNER
pedir `HOSTS`, seria `apidatalake.tesouro.gov.br`. **Não** entra agora.

O YAML declara `host: "apidatalake.tesouro.gov.br/ords/cdwhprd/siconfi/tt/"`
(caminho no campo `host`, inválido como hostname Swagger). A secção
`schemes` está **comentada**. A evidência de HTTPS é a medição HTTP,
não o campo `schemes`.

## Autenticação

Não há `security`, `apiKey`, `Authorization` nem `Bearer` no YAML
oficial (0 ocorrências; verified 2026-09-09 via
https://apidatalake.tesouro.gov.br/docs/siconfi.yaml).

Tesouro Transparente (verified 2026-09-09 via
https://www.tesourotransparente.gov.br/consultas/consultas-siconfi/siconfi-api-de-dados-abertos):

> Na API de dados abertos do Tesouro Nacional não há necessidade de
> identificação do usuário nem de remuneração pelo uso do serviço;
> deve-se apenas obedecer às orientações de uso para evitar o bloqueio
> do serviço.

O YAML (mesma data) impõe **uma requisição por segundo** “para fins de
performance”. Bloqueio por abuso -- **UNVERIFIED** (não provocámos o
limite). Captcha: a página do Tesouro Transparente afirma acesso sem
captcha; não retestámos o portal autenticado SICONFI.

O catálogo Conecta (versão Beta 1.1.0, 22/09/2020; verified 2026-09-09
via https://www.gov.br/conecta/catalogo/apis/siconfi-extratos-das-declaracoes-contabeis/)
ainda aponta o endpoint de produção em **HTTP**
`http://apidatalake.tesouro.gov.br/docs/siconfi/`. Isso é ponteiro
desactualizado: o mesmo URL responde 307 para HTTPS. Não é prova de
que a API exija HTTP.

## Licença — Apache 2.0 da API ≠ ODbL dos dados

Dois artefactos oficiais **discordam** no objecto da licença. O
primário de cada facto:

| Objecto | Licença declarada | Fonte (2026-09-09) |
|---|---|---|
| Especificação OpenAPI (`info.license`) | Apache 2.0 | `siconfi.yaml` → http://www.apache.org/licenses/LICENSE-2.0.html |
| Conjunto RREO no dados.gov.br | **ODbL** | https://dados.gov.br/dados/conjuntos-dados/api-rreo-entes |
| Conjunto DCA no dados.gov.br | **ODbL** | https://dados.gov.br/dados/conjuntos-dados/api-dca-entes |
| Conjunto RGF no dados.gov.br | **ODbL** | https://dados.gov.br/dados/conjuntos-dados/api-rgf-entes |
| Tabela de entes no dados.gov.br | **ODbL** | https://dados.gov.br/dados/conjuntos-dados/api-tabela-entes (metadados do índice; corpo SPA por vezes “Carregando…”) |

Apache 2.0 no YAML é a licença da **descrição da API** (campo Swagger
habitual). Não se trata como licença do recorte fiscal. Para os dados,
o catálogo federal aponta ODbL.

ODbL v1.0 §4.4 (verified 2026-09-09 via
https://opendatacommons.org/licenses/odbl/1-0/): qualquer **Derivative
Database** usada publicamente tem de ir sob ODbL (ou compatível);
extrair parte substancial para uma base nova **é** derivação. §4.5.c:
uso interno numa organização **não** dispara o share-alike. §4.6:
uso público de derivação exige oferecer a base derivada ou o método
das alterações.

Normalizar RREO/DCA em `MoneyEvent` e embalar no ZIP público
`public-data` é, à face do §4.4, derivação distribuída → **bloqueado
enquanto não houver análise ODbL explícita do OWNER**. Uso
operador-local de JSON original, sem redistribuir derivado, caberia
no §4.5.c; isso **não** está autorizado nesta missão e **não** muda
`not_wired`.

Código AGPL do repositório **não** relicencia SICONFI.

## Granularidade = ente federativo, nunca Place de escola/UBS

RREO e DCA são relatórios do **ente** (município, estado, DF, União,
consórcio), por exercício/período, não lançamentos a estabelecimento.

- YAML `/rreo`: “para um **ente** e período específicos”; `id_ente`
  obrigatório; `co_esfera` = M / E / U / C
  (verified 2026-09-09 via `siconfi.yaml`).
- YAML `/dca`: “para um **ente** e exercício específicos”; `id_ente`
  obrigatório (mesmo YAML).
- Modelo `RREO` / `DCA`: `instituicao` exemplo “Governo do Estado de
  Rondônia”; `cod_ibge`; `conta` / `coluna` de quadro (ex. DCA:
  `"12.363 - Ensino Profissional"`) — classificação funcional do
  **orçamento do ente**, não INEP/CNES (mesmo YAML).
- dados.gov.br RREO: anexos do RREO da União, Estados, DF e Municípios
  (verified 2026-09-09 via https://dados.gov.br/dados/conjuntos-dados/api-rreo-entes).
- dados.gov.br DCA: consolidação das contas anuais dos entes; anexos
  I-AB … I-HI (BP, BO, despesas por função, restos a pagar, DVP)
  (verified 2026-09-09 via https://dados.gov.br/dados/conjuntos-dados/api-dca-entes).
- MSC `educacao_saude`: `1` = compõe MDE, `2` = compõe ASPS — tetos
  constitucionais do **ente**, não escola nem UBS (YAML
  `MSC-Orcamentaria`).

Ligar uma linha RREO/DCA a uma escola ou UBS por nome, função
orçamentária, proximidade ou município violaria o contrato
(`facility_id` exige evidência `direct`/`reviewed`; territorial não
admite estabelecimento — `backend/bdt/domain.py`).

**Não** há, nesta evidência, identificador Inep/CNES/`facility_id`.

## Junção IBGE7 — presente no exemplo, não exclusiva no contrato

| Superfície | Campo | O que o YAML diz | IBGE7? |
|---|---|---|---|
| Query RREO / DCA / RGF / MSC / extrato | `id_ente` (integer, obrigatório) | “Código IBGE do Ente.” | Largura **não** declarada |
| Corpo Entes / RREO / DCA / RGF / Extrato / MSC | `cod_ibge` (int64) | “Código IBGE do Ente da Federação ao qual pertence a instituição”; exemplo **1718659** | O exemplo é 7 dígitos municipais; o tipo é inteiro, sem `pattern` de 7 dígitos |
| Entes.esfera | `M` / `E` / `U` / `D` | Municípios, Estados, União, DF | Estados/União/DF **não** são `municipality_id` IBGE7 do produto |

`MoneyEvent.municipality_id` exige `^[0-9]{7}$`. Um RREO estadual
(`co_esfera=E`) **não** junta a um município sem inventar IBGE7.
Códigos de UF com 1–2 dígitos na API ao vivo -- **UNVERIFIED**: não
paginámos `/entes` nem um RREO de estado (decisão do spike: sem censo).

Junção honesta, se um dia houver importador: só linhas com `cod_ibge`
de 7 dígitos e esfera municipal, para `municipality_id`;
`facility_id=None`; `relation_state=territorial`. Não é “IBGE7
verificado para todo o recorte”.

## Paginação — o que o documento diz (não o rumor)

Procurado no YAML inteiro (44 465 bytes, 1 324 linhas):

| Token | Ocorrências no YAML | Documentado? |
|---|---|---|
| `5.000 itens por página` / `5000` no texto da API | sim, em `info.description` | **sim** |
| `hasMore` / `has_more` | **0** | **UNVERIFIED** |
| `offset` | **0** | **UNVERIFIED** |
| `items` / `links` / `pagination` | **0** | **UNVERIFIED** |
| `limit` (como parâmetro de página) | não; “limit” no texto é o **1 req/s** e o “limite” MDE/ASPS | não é cursor |

Tesouro Transparente (verified 2026-09-09): JSON; “por padrão, as
consultas retornam 5.000 itens por página”. **Não** nomeia `hasMore`.

O rumor ORDS (`hasMore` / `offset`, página 5000) aparece em clientes
terceiros; **não** está nas páginas oficiais abertas neste spike.
Envelope real -- **UNVERIFIED**: HEAD `/entes` devolveu
`Content-Type: application/json` sem corpo inspecionado, de propósito.

Não há parâmetros de página em `/rreo` nem `/dca`. RREO/DCA são por
`id_ente` (+ exercício/período/anexo). Um recorte nacional seria N
entes × períodos × anexos a **1 req/s**, não uma página `hasMore`.

## Allowlist HTTPS (sem alteração)

`HOSTS` actual **não** contém `apidatalake.tesouro.gov.br` nem
`siconfi.tesouro.gov.br`. Este spike **não** altera `HOSTS`. Sem
importador, a lacuna é irrelevante.

## O que isto não é

- Não é pagamento, empenho ou transferência a escola/UBS.
- Não é Transferegov, PNCP, FNS FAF, PDDE nem SIOPS.
- Não é geometria, vaga, horário ou qualidade de serviço.
- Não certifica que todos os entes homologaram o exercício corrente
  (isso seria `/extrato_entregas` por ente/ano; não consultado).
- `not_wired` **não** é zero RREO/DCA no Brasil.

## Próximo passo (não nesta missão)

Só reabrir se o OWNER (1) aceitar operador-local de JSON original sem
ZIP público e sem `facility_id`, com análise ODbL, ou (2) pedir
explicitamente `HOSTS += apidatalake.tesouro.gov.br` depois dessa
análise. Aí: um GET de um município (IBGE7 conhecido) em um anexo
RREO, hash, envelope de paginação, e só então discutir conector.
Nada disso está autorizado agora.
