<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Migrações Alembic

O baseline `0001_baseline` representa o esquema atual criado pelo bootstrap
`Database.initialize`. Ele contém as 41 tabelas de runtime, ingestão,
colaboração, OCR, documentos e originais, e semeia as cinco tabelas de versão
com `id=1, version=1`.

`Database.initialize` continua sendo o bootstrap rápido de desenvolvimento e a
proteção aditiva para colunas opcionais. Ele **não substitui** uma migração
estrutural revisada. Alterações destrutivas, renomeações, índices e mudanças de
constraint pertencem a uma revisão Alembic.

## Banco novo

```bash
python -m bdt.migrate upgrade --database sqlite:///data/bdt.db
# ou PostgreSQL: --database postgresql+psycopg://...
python -m bdt.migrate check --database ...
```

O `upgrade` cria o esquema completo e registra `0001_baseline` em
`alembic_version`. O `check` compara o banco com `Base.metadata` e falha se
houver deriva. A URL passada em `--database` **vence** uma variável
`BDT_DATABASE_URL` herdada; a variável só é usada quando nenhuma URL foi
passada.

## Banco existente

Antes da primeira migração futura, marque o banco existente como baseline. Não
rode `upgrade` em um banco não marcado: o Alembic tentará criar tabelas que já
existem.

```bash
python -m bdt.migrate stamp --database postgresql+psycopg://...
python -m bdt.migrate upgrade --database postgresql+psycopg://...
python -m bdt.migrate current --database postgresql+psycopg://...
```

Faça backup consistente e teste a restauração antes de `stamp`/`upgrade` em
produção. `downgrade` do baseline derruba todas as tabelas; ele não é um
procedimento de recuperação e exige decisão explícita com backup.

## Estrutura

- `alembic.ini`: configuração, sem URL/segredo fixo.
- `migrations/env.py`: importa todos os módulos de modelo; a URL da CLI vence
  `BDT_DATABASE_URL`, que é o fallback.
- `migrations/versions/`: revisões; a baseline é `0001_baseline`.
- `backend/bdt/migrate.py`: comandos de operador `upgrade`, `stamp`, `current`
  e `check`. Em instalação fora do checkout, defina `BDT_PROJECT_ROOT` para o
  diretório que contém `alembic.ini` e `migrations/`.

## Evidência

- SQLite descartável: upgrade, tabelas completas, seed de versão, `check` sem
  deriva e `Database.initialize` posterior.
- PostgreSQL 16 efêmero: `upgrade` e `check` executados em banco novo
  `bdt_migration`, com resultado `No new upgrade operations detected`; banco
  removido em seguida.
- O lock Linux verificado inclui `alembic==1.20.0`, `mako==1.4.3` e
  `markupsafe==3.0.4` (51 pacotes no total, incluindo o extra MCP que estava
  ausente do lock anterior).

## Limites

A migração tradicional de dados de versões anteriores, o downgrade seguro, o
PITR, a restauração de produção e a execução multi-réplica sem DDL concorrente
continuam gates de infraestrutura. O baseline foi validado em bancos vazios;
não há um banco de produção histórico para ensaiar.
