<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Restore ensaiado do backup PostgreSQL local

Lote de 21/10/2026. Base de integração no `main`: `0042682`. Código em
`e199dc7dbb201a242a7de762d78e03ad2f66ad48`.

## O que mudou

- `ops/postgres-backup.sh` permite nome fixo (`BDT_BACKUP_NAME`) e grava um
  dump `pg_dump -Fc` no volume privado `bdt-postgres-backups`.
- `ops/postgres-restore.sh` cria um banco **novo** com owner `bdt_app`, executa
  `pg_restore --no-owner --no-privileges --role=bdt_app`, confere
  `alembic_version` e a contagem de tabelas. Destino existente, nome inválido,
  `postgres`, `template0` ou `template1` são recusados.
- O Compose ganhou o serviço `postgres-restore` no profile `ops`, com o volume
  de backup montado somente para leitura e a mesma rede interna.
- O job `postgres-stack` do `Runtime integration` agora executa backup e restore
  com nome fixo `bdt-ci.dump` e verifica `0001_baseline` no banco restaurado.
- O restore nunca sobrescreve o banco da aplicação; ele cria um destino separado
  e deixa a decisão de troca para o operador.

## Evidência local

- Stack local em `:8009` healthy.
- Backup `bdt-ci-restore.dump` gerado no volume.
- Restore em `bdt_restore_ci` concluído: `alembic_version = 0001_baseline` e
  **42 tabelas** no schema público.
- O banco de restore foi removido depois; o banco da aplicação permaneceu
  intacto.
- `docker compose -f compose.postgres.yaml config --quiet` aprovado.
- Nenhum código Python mudou; a suíte anterior permanece **2.192 aprovados,
  17 ignorados** e a web **243 aprovados** com build Vite 8.2.4.

## Limites

É um ensaio **local**: o dump fica no mesmo host, não há PITR, backup offsite,
retenção, criptografia de backup, restauração automatizada em produção ou troca
de banco com rollback. A restauração não valida a qualidade dos dados nem
credenciais de produção. A Issue #21 pode ser encerrada com esta evidência;
Issues #2–#5 continuam abertas.
