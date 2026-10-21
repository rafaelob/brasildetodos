<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Baseline Alembic e lock Linux atualizado

Lote de 21/10/2026. Base de integração no `main`: `ddec65a`. O código deste
lote está em `f05d168`.

## O que mudou

- Adotado `alembic==1.20.0` como extra `migration`, com `alembic.ini`,
  `migrations/env.py` e a revisão baseline `0001_baseline`.
- O baseline cria as **41 tabelas** de runtime, ingestão, colaboração, OCR,
  documentos e originais, e semeia `schema_version`, `extension_version`,
  `photo_schema_version`, `group_schema_version` e `ocr_queue_version` com
  `id=1, version=1`.
- `bdt.migrate` oferece `upgrade`, `stamp`, `current` e `check`. A URL vem de
  `BDT_DATABASE_URL` ou de `--database`; não há URL/segredo fixo no repositório.
- Banco novo usa `upgrade`; banco existente usa `stamp` uma vez antes de futuras
  migrações. `check` detecta deriva entre `Base.metadata` e o banco.
- O lock Linux foi regenerado com pip-tools 7.6.1/Python 3.14.8: **51 pacotes**.
  Ele agora inclui `alembic`, `mako`, `markupsafe` e o extra MCP que estava
  ausente do lock anterior (14 pacotes), além das dependências já existentes.
- Docker e Compose copiam `alembic.ini`/`migrations` e definem
  `BDT_PROJECT_ROOT=/app`. `Quality` e `Runtime integration` observam os novos
  arquivos.

## Evidência local

- Suíte Python integral em `f05d168`: **2.186 aprovados, 17 ignorados, zero
  falhas** (6m55s). Dois avisos não bloqueantes: depreciação de
  `anyio.abc.BlockingPortal` no TestClient e Operation ID duplicado para
  `/api/health`.
- Testes de migração SQLite: **3 aprovados** — upgrade completo, tabelas/seed,
  `check`, stamp de banco já inicializado e detecção de deriva após remover uma
  tabela.
- PostgreSQL 16 efêmero: banco novo `bdt_migration`, `upgrade` para
  `0001_baseline` e `check` com **“No new upgrade operations detected”**; banco
  descartável removido ao final.
- Lock verificado: instalação hash-checked, 51 pacotes, `pip check` sem quebra.
- `python -m compileall` e `git diff --check` aprovados.

## Limites

Não houve migração de dados históricos, downgrade seguro, PITR, restauração de
produção, ensaio multi-réplica ou migração de um banco produtivo real. O
baseline foi validado em bancos vazios e em banco bootstrapado seguido de
`stamp`. Windows/macOS continuam sem lock próprio. As Issues #4 e #5 permanecem
abertas.
