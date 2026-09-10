<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Restante — cache local CNEFE 2022 (`data/cnefe_cache/`)

Nota de operador. Instantes de `stat`: **2026-09-09T23:17:24-03:00** e
**2026-09-09T23:18:07-03:00** (tamanhos idênticos). Arquivo nomeado na
onda **20260910**. Só o sistema de arquivos: `Length` e 4 bytes de
assinatura ZIP (`50 4B 03 04`). **Não** descompactar. **Não** FTP.
**Não** HTTP a `ftp.ibge.gov.br`. Este processo **não** definiu
`BDT_CNEFE_OPERATOR_DOWNLOAD`.

Contrato no código: `backend/bdt/school_geocoder.py`
(`STATE_IBGE_CODES`, 27 UFs; `download_cnefe_state_zip`). Diretório
padrão: `ops/geocode_schools_cnefe.py --cache-dir` → `data/cnefe_cache`.
Padrão de arquivo: `{código_IBGE}_{UF}.zip`. Inventário anterior:
[20260909-cnefe-cache-inventory.md](20260909-cnefe-cache-inventory.md)
(11 presentes, 16 faltas documentadas).

## O que fazer

1. ZIP ausente = **falta documentada de arquivo**, nunca “zero escolas”
   na UF e nunca cobertura nacional.
2. Não acrescente `ftp.ibge.gov.br` a `bdt.ingest.HOSTS`. A exceção
   `BDT_CNEFE_OPERATOR_DOWNLOAD=1` **não** é expansão da allowlist HTTPS
   e **não** autoriza `bdt download` nesse host.
3. Não invente coordenadas. Match de nome grava
   `payload.cnefe_candidate` e **não** copia lat/lon para
   `Place.latitude` / `Place.longitude` nem `geo_source`. Candidato
   inédito **não** é pino no mapa.
4. `GET /api/coverage` continua a verdade desta instalação.
   `national_catalog_certified` permanece **`false`** mesmo com 27 ZIPs
   em cache.

O default de `python ops/geocode_schools_cnefe.py` é `--states RR AP AC SE RO`
(recorte de 5 UFs), não as 27. Esta nota **não** rodou o geocoder.

## Instantâneo (27 / 27)

**Presentes: 27. Faltas neste instante: nenhuma.**

Bytes = `Length` no disco. `mtime` local **não** é data de referência do
Censo 2022. Membros CSV, SHA-256 e contagem de estabelecimentos de ensino
**não** foram lidos.

| UF | Código IBGE | Arquivo | Bytes | Neste clone desde |
|---|---|---|---:|---|
| RO | 11 | `11_RO.zip` | 16.310.880 | 2026-09-08 (inventário 09) |
| AC | 12 | `12_AC.zip` | 7.023.748 | 2026-09-08 (inventário 09) |
| AM | 13 | `13_AM.zip` | 29.620.766 | 2026-09-09T23:14:26 |
| RR | 14 | `14_RR.zip` | 4.520.527 | 2026-09-08 (inventário 09) |
| PA | 15 | `15_PA.zip` | 103.050.645 | 2026-09-09T23:14:30 |
| AP | 16 | `16_AP.zip` | 5.454.312 | 2026-09-08 (inventário 09) |
| TO | 17 | `17_TO.zip` | 15.412.488 | 2026-09-08 (inventário 09) |
| MA | 21 | `21_MA.zip` | 77.694.765 | 2026-09-09T23:14:34 |
| PI | 22 | `22_PI.zip` | 34.838.556 | 2026-09-09T23:14:36 |
| CE | 23 | `23_CE.zip` | 138.747.815 | 2026-09-09T23:14:43 |
| RN | 24 | `24_RN.zip` | 34.231.013 | 2026-09-08 (inventário 09) |
| PB | 25 | `25_PB.zip` | 40.796.565 | 2026-09-08 (inventário 09) |
| PE | 26 | `26_PE.zip` | 151.432.961 | 2026-09-09T23:14:49 |
| AL | 27 | `27_AL.zip` | 29.180.557 | 2026-09-08 (inventário 09) |
| SE | 28 | `28_SE.zip` | 20.632.480 | 2026-09-08 (inventário 09) |
| BA | 29 | `29_BA.zip` | 398.181.853 | 2026-09-09T23:15:05 |
| MG | 31 | `31_MG.zip` | 537.151.309 | 2026-09-09T23:15:25 |
| ES | 32 | `32_ES.zip` | 41.567.902 | 2026-09-09T23:15:28 |
| RJ | 33 | `33_RJ.zip` | 338.096.849 | 2026-09-09T23:15:40 |
| SP | 35 | `35_SP.zip` | 1.082.015.432 | 2026-09-09T23:16:21 |
| PR | 41 | `41_PR.zip` | 242.066.031 | 2026-09-09T23:16:29 |
| SC | 42 | `42_SC.zip` | 118.607.932 | 2026-09-09T23:16:33 |
| RS | 43 | `43_RS.zip` | 247.249.924 | 2026-09-09T23:16:43 |
| MS | 50 | `50_MS.zip` | 29.787.554 | 2026-09-08 (inventário 09) |
| MT | 51 | `51_MT.zip` | 37.772.175 | 2026-09-09T23:16:45 |
| GO | 52 | `52_GO.zip` | 120.818.046 | 2026-09-09T23:16:50 |
| DF | 53 | `53_DF.zip` | 19.814.349 | 2026-09-08 (inventário 09) |

Soma: **3.922.077.434** bytes. Vinte e sete arquivos; nenhum extra; nenhum
vazio. Cabeçalho local de cada um: `50 4B 03 04` (ZIP).

Os 16 que o inventário de 09/09 listava como falta (AM, PA, MA, PI, CE,
PE, BA, MG, ES, RJ, SP, PR, SC, RS, MT, GO) apareceram em disco durante
esta inspeção. Este processo não os descarregou e não inspecionou o
comando que os gravou.

## Faltas documentadas (0 neste instante)

Lista: **(vazia)**.

Regra que permanece: se um `{código}_{UF}.zip` desaparecer, isso é
**falta documentada**, não “zero escolas” Inep/CNEFE nessa UF.
`download_cnefe_state_zip` recusa o miss com `ValueError` a nomear o
arquivo, `HOSTS` e `BDT_CNEFE_OPERATOR_DOWNLOAD`, sem contato de rede,
salvo a exceção explícita abaixo.

## Allowlist e exceção de operador

`bdt.ingest.HOSTS` (lido em `backend/bdt/ingest.py`):
`servicodados.ibge.gov.br`, `apidadosabertos.saude.gov.br`,
`download.inep.gov.br`, `dadosabertos.saude.gov.br`,
`repositorio.dados.gov.br`, `repositorio.transferegov.gestao.gov.br`,
`api-publica.transferegov.gestao.gov.br`,
`api-publica.obrasgov.gestao.gov.br`, `pncp.gov.br`.
**Não** contém `ftp.ibge.gov.br`. Testes:
`backend/tests/test_ingest.py` (`test_ftp_ibge_host_is_not_in_allowlist`),
`backend/tests/test_ibge_cache_first.py`
(`test_cnefe_ftp_is_rejected_by_shipped_allowlist`).

`BDT_CNEFE_OPERATOR_DOWNLOAD=1` faz `download_cnefe_state_zip` contactar
`CNEFE_BASE` (`https://ftp.ibge.gov.br/.../CSV/UF/{código}_{UF}.zip`) e
gravar o ZIP no cache. Isso é **exceção de operador**, não inclusão do
host em `HOSTS`. `bdt download` / `safe_download` continuam a recusar o
FTP. Sem a variável, cache miss não baixa.

## Candidatos inéditos, não pinos

`geocode_schools_for_state` só persiste `payload.cnefe_candidate`
(`lat`, `lon`, `cnefe_name`, `match=exact_name`) após nome normalizado
exato no mesmo `COD_MUNICIPIO`. Duplicados ambíguos no município são
descartados na análise. Não é dicionário Inep↔CNEFE. Não gera geometria
publicada. Sem dicionário oficial de identificadores, 27 ZIPs no cache
não viram pinos.

`national_catalog_certified` é `False` em
`backend/bdt/coverage_dashboard.py` (`build_coverage`, `read_imports`) e
não muda por existir cache CNEFE.

## O que isto não prova

- Não é cobertura nacional do CNEFE 2022 nem do Censo Escolar.
- Não conta escolas, municípios nem `cnefe_candidate` gravados neste clone.
- Não publica geometria. Não inventa coordenadas.
- Não certifica o catálogo. 27 ZIPs ≠ Brasil inteiro na API.
- SHA-256, membros CSV e integridade além da assinatura local ZIP
  permanecem **UNVERIFIED**.
- Não se afirma que a exceção de operador esteve ligada no processo que
  gravou os 16 ZIPs novos — só que os ficheiros passaram a existir.
