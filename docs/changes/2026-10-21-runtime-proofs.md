<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Prova PostgreSQL efêmera e renderização real com Poppler

Lote de 21/10/2026. Base de integração no `main`: `1436f8e`. A correção do
worker documental está em `9bdcfe0`.

## PostgreSQL real, efêmero

- `docker compose --profile test up --build --abort-on-container-exit --exit-code-from postgres-proof postgres-proof`
  subiu `postgres:16-bookworm` pelo digest fixado e executou
  `tests/runtime/test_postgres_runtime.py`.
- Resultado: **4 aprovados**. O recibo
  `test-results/runtime/postgres.json` registra:
  `non_superuser_database_role`, `schema_initialized_twice`,
  `foreign_keys_unique_constraints_and_indexes`,
  `constraint_failure_rolled_back`, `schema_ddl_failure_rolled_back`,
  `concurrent_schema_initializers_serialized`,
  `quoted_schema_defaults_and_foreign_keys`,
  `postgres_repeatable_snapshot_to_sqlite_public_install`, entre outros.
- O banco de prova usa `tmpfs`, rede interna sem porta publicada, usuário
  `bdt_ci` sem superusuário e é explicitamente efêmero. O recibo declara
  `production_deployed: false`.
- Os containers, rede e volume temporários foram removidos com
  `docker compose --profile test down -v --remove-orphans`.

## Worker documental

- `ops/Dockerfile.documents` usava `python:3.13-slim-bookworm`, incompatível com
  `requires-python == 3.14.8`; o build falhava antes de instalar o projeto.
- O worker passou a usar `python:3.14.8-slim-bookworm`, a instalar pelo
  `ops/install_locked.py` com o lock Linux verificado e a manter Poppler,
  Tesseract português/inglês/espanhol.
- O build real foi concluído. Em seguida, um PDF sintético de uma página foi
  renderizado dentro do container com `bdt.document_render.render_page`:
  **15.002 bytes**, SHA-256
  `d8909ddd036cb0370556ab461b53cbbba7fd4965a2f931dff25beb0e83e1ff47`,
  cabeçalho PNG confirmado.
- O container foi executado com `--network none`, `--read-only`, `--tmpfs /tmp`,
  `--cap-drop ALL` e `no-new-privileges`; o PDF entrou somente como volume de
  leitura.

## Evidência local

- Suíte Python integral anterior à alteração do Dockerfile: **2.183 aprovados,
  17 ignorados, zero falhas** em `d458b4a`.
- Web: **243 aprovados, zero falhas**; build Vite 8.2.4 aprovado.
- PostgreSQL: **4 aprovados** no Compose efêmero.
- Poppler: renderização real de uma página sintética no worker documental.
- Este lote não alterou código Python; a prova de container é a aceitação da
  correção.

## Limites

O PostgreSQL provado é **efêmero**, não produção: não há volume durável,
backup/restauração de produção, PITR, failover ou retenção. O worker documental
foi validado com um PDF sintético, não com corpus oficial. O renderizador
continua opcional e não publica páginas. Alembic, deploy público, domínio/HTTPS
e upload de imagens em grupos permanecem pendentes. As Issues #4 e #5 continuam
abertas.
