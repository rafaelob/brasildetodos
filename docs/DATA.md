<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Fontes e integração

Significados e edições certificadas vivem em [`docs/SOURCES.md`](SOURCES.md).
Este arquivo é o procedimento file-first: encoding, `--member`, perfis revisados
e carga dos municípios IBGE primeiro.

Aceitar um arquivo não comprova cobertura nacional. Publique a referência da
edição, URL original, SHA-256 dos bytes, contagem/partição e problemas. Não
baixe todos os PDFs indiscriminadamente nem contorne autenticação ou limites de
requisição. A CLI de operador corre fora da requisição web.

## Ordem

1. `bdt init-db` no banco de destino (`--database` ou `BDT_DATABASE_URL`;
   omissão: `sqlite:///data/bdt.db`).
2. Carregar municípios IBGE. Lugares recusam município desconhecido ou UF
   inconsistente. CNES e Inep ainda precisam do cruzamento: código de 6 dígitos
   só converte a partir dos IBGE7 carregados. Finanças apontam FK para essa
   tabela.
3. Importar cadastros de lugares (Inep, CNES, `import-places`).
4. Importar finanças e metadados de recursos.

Carga nacional de operador e instalação de edição certificada são outros
passos: [EDUCATION_PIPELINE.md](EDUCATION_PIPELINE.md),
[CNES_QUALITY.md](CNES_QUALITY.md),
[UNIFIED_INSTALLATION.md](UNIFIED_INSTALLATION.md).

## Proveniência e download

`import-ibge`, `import-cnes`, `import-inep`, `import-places`, `import-finance`
e `import-transferegov` exigem `--url` (HTTP/HTTPS público, sem usuário na URL)
e `--reference-date`. O SHA-256 é o dos bytes do arquivo. O campo `source` no
JSON de lugar ou finança é substituído por essa proveniência.

```bash
bdt download https://servicodados.ibge.gov.br/api/v1/localidades/municipios data/municipios.json
```

`bdt download` só aceita HTTPS nos hosts revisados, porta 443, endereço público,
resposta 200 sem redirecionamento e corpo não vazio. Teto padrão: 256 MiB
(`--max-bytes`). Grava o arquivo e `*.manifest.json` (`url`, `sha256`, `bytes`,
`collected_at`, `etag`, `status_code`). Hosts: `servicodados.ibge.gov.br`,
`apidadosabertos.saude.gov.br`, `download.inep.gov.br`,
`dadosabertos.saude.gov.br`, `repositorio.dados.gov.br`,
`repositorio.transferegov.gestao.gov.br`,
`api-publica.transferegov.gestao.gov.br`,
`api-publica.obrasgov.gestao.gov.br`, `pncp.gov.br`.

Não desabilite TLS e não use HTTP. O ZIP do catálogo CNES na distribuição S3
**não** passa por `bdt download`; use [CNES_QUALITY.md](CNES_QUALITY.md).

## Encoding, `--member` e perfis

- `--encoding` vale só para CSV. Padrão da CLI: `utf-8-sig`. JSON (IBGE, CNES
  objeto/array, places, finance) é sempre `utf-8-sig` e **ignora** a flag.
  Inep: o microdado costuma ser `cp1252`; a CLI **não** detecta sozinha — passe
  `--encoding` conferido no dicionário da edição.
- `--member` é o caminho exato do CSV dentro do ZIP, usado quando o importador
  lê CSV (Inep sempre; Transferegov sempre; CNES/places só se o sufixo do path
  for `.csv`). Sem `--member`, o path é o próprio CSV. Nenhum membro é extraído
  em disco. Membro diretório, maior que 4 GiB ou com razão de compressão acima
  de 500 é recusado. `import-cnes` em arquivo `.zip` **não** usa `--member`:
  sufixo `.zip` é lido como JSON. O ZIP oficial com cabeçalhos `CO_CNES` é
  [CNES_QUALITY.md](CNES_QUALITY.md), não este comando.
- `--root` seleciona o array em JSON de CNES/places. Sem `--root`, o arquivo
  deve ser um array. IBGE e `import-finance` ignoram `--root`.
- `--profile` é obrigatório em `import-transferegov`: JSON UTF-8 com exatamente
  `columns`, `phase`, `nature` e `perspective`.

CSV usa delimitador `;` (não há flag para outro). Schema desconhecido, ID
repetido no arquivo ou município ausente no cruzamento falham o lote inteiro.

## IBGE

JSON array. Cada `id` é IBGE7 numérico, sem duplicata. O parser aceita
`microrregiao` / `mesorregiao` / `UF` ou `regiao-imediata` /
`regiao-intermediaria` / `UF`. Arquivo vazio não é carga válida.

```bash
bdt import-ibge data/municipios.json \
  --url https://servicodados.ibge.gov.br/api/v1/localidades/municipios \
  --reference-date DATA_DA_EDICAO
```

Substitua `DATA_DA_EDICAO` pela referência efetiva. Você deve ver
`"municipalities": <N>` e `"scope": "provided_file"`.

## Inep

Antes de executar, confira o dicionário da edição. Cabeçalhos exigidos:
`CO_ENTIDADE`, `NO_ENTIDADE`, `CO_MUNICIPIO`, `TP_DEPENDENCIA`,
`TP_SITUACAO_FUNCIONAMENTO`. Somente públicas ativas (`TP_DEPENDENCIA` 1/2/3 e
`TP_SITUACAO_FUNCIONAMENTO` 1). Endereço sem coordenadas continua consultável;
pares inválidos (incluindo 0,0) viram nulos — a caixa aceita latitude −35…6 e
longitude −75…−32. O comando aceita arquivo nacional; não corrige sozinho
mudança de esquema entre edições.

```bash
bdt import-inep data/censo.zip --member CAMINHO_EXATO_DA_TABELA.csv \
  --encoding cp1252 --url URL_OFICIAL_DO_ARQUIVO --reference-date ANO_BASE
```

Você deve ver `"coverage": "provided_file_only"` e `counts` com `read`,
`inserted`/`updated`/`unchanged`, `excluded` e `without_geometry`.

## CNES

`bdt import-cnes` espera os campos da API JSON: `codigo_cnes`, `nome_fantasia`,
`codigo_municipio`, `estabelecimento_faz_atendimento_ambulatorial_sus` (não
`possui`). Recorte: atendimento ambulatorial SUS declarado (`SIM` / `S` / `1`)
e `codigo_motivo_desabilitacao_estabelecimento` vazio. Gestão municipal com
atendimento SUS `NAO` é excluída — gestão não certifica elegibilidade.
`data_atualizacao` da linha prevalece sobre `--reference-date` quando presente.
Telefone não é garantia de atendimento.

```bash
bdt import-cnes data/cnes.json --root estabelecimentos \
  --url URL_OFICIAL_DA_EDICAO --reference-date COMPETENCIA
```

A primeira página da API não é o Brasil. Inspeção de 2026-09-05: chamada sem
filtros devolveu cinco registros. **Não existe paginação nacional certificada
neste importador.** Use export oficial completo ou a carga em lote. CSV com
sufixo `.csv` usa os **mesmos** nomes da API, não os cabeçalhos `CO_CNES` do
ZIP de catálogo (esse ZIP é [CNES_QUALITY.md](CNES_QUALITY.md)).

## Transferegov (CSV + perfil)

Não é integração de todas as tabelas. O perfil JSON tem exatamente:

```json
{
  "columns": {
    "id": "COLUNA_ID",
    "municipality_id": "COLUNA_MUNICIPIO",
    "instrument_id": "COLUNA_INSTRUMENTO",
    "recipient": "COLUNA_FAVORECIDO",
    "period": "COLUNA_PERIODO",
    "amount": "COLUNA_VALOR"
  },
  "phase": "transferred",
  "nature": "event",
  "perspective": "federal"
}
```

`phase`: `estimated` | `agreed` | `committed` | `transferred` | `contracted` |
`liquidated` | `paid`. `nature`: `event` | `cumulative` | `estimate`.
`perspective`: `federal` | `state` | `municipal` | `executing_unit`. Os
cabeçalhos do CSV devem coincidir com os valores de `columns`. `municipality_id`
já em IBGE7 — este comando **não** aplica o cruzamento de 6 dígitos. Quantia em
notação brasileira com centavos (`1.200,00`). Pré-convênio não é instrumento
assinado: filtre condição/escopo no perfil antes de publicar.

```bash
bdt import-transferegov data/arquivo.csv --profile data/perfil-revisado.json \
  --url URL_OFICIAL --reference-date DATA_REFERENCIA
```

ZIP: acrescente `--member` (e `--encoding` se não for `utf-8-sig`). Download
antigo acessível não comprova atualização. `bdt import-transferegov-finance` é
outro caminho (ZIP SICONV; padrão `data/downloads/transferegov`) e não substitui
o perfil revisado.

## Finanças normalizadas

```bash
bdt import-finance arquivo.json --url URL --reference-date REFERENCIA
```

JSON array. Contrato `MoneyEvent` em `backend/bdt/domain.py`. Campos
obrigatórios: `id`, `municipality_id` (IBGE7), `instrument_id`, `phase`,
`cents` (inteiro), `period` (`YYYY`, `YYYY-MM` ou `YYYY-MM-DD`), `recipient`,
`perspective`. `nature` omisso = `event`. `relation_state` omisso =
`territorial`. `facility_id` só com `relation_state` `direct` ou `reviewed` e
`evidence`. Natureza event/cumulative/estimate muda a agregação; fases não se
somam.

## PNCP, planos e obras

Metadados versionados via `bdt sync-resources`, não pagamentos. Detalhe:
[RESOURCE_INGESTION.md](RESOURCE_INGESTION.md). Importe IBGE antes. Sem
`--collect`, só importa a pasta já coletada. Janela PNCP é `YYYYMMDD` e no
máximo 32 dias; `page-size` 10–500.

```bash
bdt sync-resources pncp_contracts --folder data/collections/pncp-YYYYMMDD \
  --start YYYYMMDD --end YYYYMMDD --collect
bdt import-places data/obras.json --url URL_DA_FONTE --reference-date REFERENCIA
```

`import-places` lê JSON canônico: `id` no padrão `prefixo:chave`, `kind`
`school` | `health` | `work`, `name`, `municipality_id` IBGE7, `state` UF.
Nenhuma coordenada é inferida do comprador. A evidência para `facility_id` em
finanças deve ser revisada.

## Falha e verificação

Falha (e reverte o arquivo) por schema desconhecido, ID repetido no input,
município não carregado no cruzamento CNES/Inep, ou correção financeira sem
reconciliação (valor anterior preservado). Input vazio não é sucesso. Não
substitua falta de dado por 0, coordenada aproximada ou promessa de
vaga/consulta.

Sucesso de lugares grava ingestão `completed_file` e
`"coverage": "provided_file_only"` — inclusive quando o arquivo é nacional.
Leia `excluded` no JSON da CLI e as falhas em `GET /api/imports` antes de
disponibilização pública. Ineligibilidade explícita retira o lugar da busca e
conserva histórico; ausência de um ID num arquivo parcial não fecha o registro
anterior.

Totais de edições certificadas e o mapa conector × esta instalação:
[SOURCES.md](SOURCES.md).
