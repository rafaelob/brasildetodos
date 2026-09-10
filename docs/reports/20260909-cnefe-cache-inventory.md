<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Inventário — cache local CNEFE 2022 (`data/cnefe_cache/`)

Data do inventário: **2026-09-09**. Apenas `stat` no sistema de arquivos e
assinatura local ZIP (`PK\x03\x04`, 4 bytes). **Não** descompactar o país.
**Não** FTP. **Não** HTTP a `ftp.ibge.gov.br`. `BDT_CNEFE_OPERATOR_DOWNLOAD`
não foi definido. `HOSTS` **não** foi alterado.

Fonte de nomes: `backend/bdt/school_geocoder.py` (`STATE_IBGE_CODES`,
`download_cnefe_state_zip`). Diretório padrão do operador:
`ops/geocode_schools_cnefe.py --cache-dir` → `data/cnefe_cache`.
Padrão de arquivo: `{código_IBGE}_{UF}.zip`.

## Conclusão

Há **11** arquivos locais com tamanho > 0. Há **16** UFs das 27 em
`STATE_IBGE_CODES` **sem** ZIP no cache — isso é **falta documentada de
arquivo**, não “zero escolas” nesses estados e não cobertura do Brasil.

`national_catalog_certified` permanece **`false`**. Um match de nome
grava `payload.cnefe_candidate` (lat/lon do estabelecimento CNEFE,
`match=exact_name`) e **não** copia coordenadas para `Place.latitude` /
`Place.longitude` nem `geo_source`. Sem dicionário oficial de
identificadores, candidato inédito não é pino no mapa.

As 16 UFs restantes ficam bloqueadas neste clone porque `ftp.ibge.gov.br`
**não** está em `bdt.ingest.HOSTS`. Existe exceção de operador
(`BDT_CNEFE_OPERATOR_DOWNLOAD=1`); esta onda **não** a usa, **não**
expande `HOSTS` e **não** transfere por FTP.

## Presentes (11)

Bytes = `Length` do arquivo no disco. `mtime` local **não** é data de
referência do Censo 2022.

| UF | Código IBGE | Arquivo | Bytes |
|---|---|---|---:|
| RO | 11 | `11_RO.zip` | 16 310 880 |
| AC | 12 | `12_AC.zip` | 7 023 748 |
| RR | 14 | `14_RR.zip` | 4 520 527 |
| AP | 16 | `16_AP.zip` | 5 454 312 |
| TO | 17 | `17_TO.zip` | 15 412 488 |
| RN | 24 | `24_RN.zip` | 34 231 013 |
| PB | 25 | `25_PB.zip` | 40 796 565 |
| AL | 27 | `27_AL.zip` | 29 180 557 |
| SE | 28 | `28_SE.zip` | 20 632 480 |
| MS | 50 | `50_MS.zip` | 29 787 554 |
| DF | 53 | `53_DF.zip` | 19 814 349 |

Soma: **223 164 473** bytes. Onze arquivos; nenhum extra; nenhum vazio.
Cabeçalho local de cada um: `50 4B 03 04` (ZIP). Membros CSV, hashes
SHA-256 e contagem de estabelecimentos de ensino **não** foram lidos.

## Faltas documentadas (16)

Ausência no cache ≠ ausência de escolas oficiais (Inep) nessas UFs.
`download_cnefe_state_zip` recusa o miss com `ValueError` a nomear o
arquivo, `HOSTS` e `BDT_CNEFE_OPERATOR_DOWNLOAD`, sem contato de rede.

| UF | Código IBGE | Arquivo esperado | Estado |
|---|---|---|---|
| AM | 13 | `13_AM.zip` | **falta documentada** |
| PA | 15 | `15_PA.zip` | **falta documentada** |
| MA | 21 | `21_MA.zip` | **falta documentada** |
| PI | 22 | `22_PI.zip` | **falta documentada** |
| CE | 23 | `23_CE.zip` | **falta documentada** |
| PE | 26 | `26_PE.zip` | **falta documentada** |
| BA | 29 | `29_BA.zip` | **falta documentada** |
| MG | 31 | `31_MG.zip` | **falta documentada** |
| ES | 32 | `32_ES.zip` | **falta documentada** |
| RJ | 33 | `33_RJ.zip` | **falta documentada** |
| SP | 35 | `35_SP.zip` | **falta documentada** |
| PR | 41 | `41_PR.zip` | **falta documentada** |
| SC | 42 | `42_SC.zip` | **falta documentada** |
| RS | 43 | `43_RS.zip` | **falta documentada** |
| MT | 51 | `51_MT.zip` | **falta documentada** |
| GO | 52 | `52_GO.zip` | **falta documentada** |

Lista: **AM, PA, MA, PI, CE, PE, BA, MG, ES, RJ, SP, PR, SC, RS, MT, GO**.

## Contrato no código (não inventar pinos)

- Cache hit: lê o ZIP local se `is_file()` e `st_size > 0`.
- Cache miss sem `BDT_CNEFE_OPERATOR_DOWNLOAD=1`: levanta; não baixa.
- URL no código (`CNEFE_BASE` em `https://ftp.ibge.gov.br/.../CSV/UF/{código}_{UF}.zip`)
  **não** foi contactada nesta inspeção.
- `bdt.ingest.HOSTS` (lido em `backend/bdt/ingest.py`):
  `servicodados.ibge.gov.br`, `apidadosabertos.saude.gov.br`,
  `download.inep.gov.br`, `dadosabertos.saude.gov.br`,
  `repositorio.dados.gov.br`, `repositorio.transferegov.gestao.gov.br`,
  `api-publica.transferegov.gestao.gov.br`,
  `api-publica.obrasgov.gestao.gov.br`, `pncp.gov.br`.
  **Não** contém `ftp.ibge.gov.br`.
- Match: nome normalizado exato no mesmo `COD_MUNICIPIO`; duplicados
  ambíguos no município são descartados na análise. Não é dicionário
  Inep↔CNEFE. Não gera latitude/longitude em `Place`.

CLI de operador (`python ops/geocode_schools_cnefe.py`) usa o mesmo
cache. O default `--states RR AP AC SE RO` é um recorte, não as 11 UFs
em disco e não as 27 do país.

## O que isto não prova

- Não é cobertura nacional do CNEFE 2022 nem do Censo Escolar.
- Não conta escolas, municípios nem candidatos gravados neste clone.
- Não publica geometria. Não inventa coordenadas para UFs em falta.
- `GET /api/coverage` continua a ser a verdade da instalação;
  `national_catalog_certified` não muda por existirem 11 ZIPs em cache.
