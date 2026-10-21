<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Stack PostgreSQL local durável

Lote de 21/10/2026. Base de integração no `main`: `d3f03e2`. O Compose está em
`d6b1dde`.

## O que mudou

- `compose.postgres.yaml` adiciona um stack local separado, com:
  - PostgreSQL 16 no digest fixado e volume `bdt-postgres-data`;
  - volume `bdt-postgres-originals` para o store privado;
  - serviço one-shot `migrate` que roda `python -m bdt.migrate upgrade`;
  - aplicação em `127.0.0.1:8009`, dependente da migração concluída;
  - healthchecks, `read_only`, `cap_drop`, `no-new-privileges` e limites;
  - perfil `ops` com `postgres-backup` e volume `bdt-postgres-backups`.
- `ops/postgres-local-init.sql` cria o papel `bdt_app` sem superusuário,
  `CREATEDB` ou `CREATEROLE`, dono do banco `bdt_app`.
- A autenticação `trust` é limitada à rede interna `backend`; o PostgreSQL não
  publica porta. A aplicação entra também na rede `edge` para o bind local.
- `BDT_POSTGRES_PORT`/`BDT_POSTGRES_ORIGIN` permitem mudar a porta/origem local;
  os padrões são `8009` e `http://127.0.0.1:8009`.
- `down` preserva os volumes; `down -v` apaga dados e originais.
- O workflow `Runtime integration` ganhou o job `postgres-stack`, que sobe esse
  Compose, aguarda o health, confere `0001_baseline`, executa o backup local e
  remove os volumes ao final.

## Evidência local

- `docker compose -f compose.postgres.yaml up --build -d` concluiu; `migrate`
  saiu com sucesso e `app` ficou `healthy`.
- `GET http://127.0.0.1:8009/api/health` retornou
  `{"status":"ok","version":"0.1.0","llm_required":false}`.
- Dentro do banco: `alembic_version = 0001_baseline` e **42 tabelas** no schema
  público (41 do baseline + `alembic_version`).
- `postgres-backup` gerou `bdt-20261021T173808.dump` com **106 KiB** no volume
  de backup.
- `down` sem `-v` seguido de `up` preservou o banco; `alembic_version` continuou
  `0001_baseline` e o health voltou a responder.
- Ao final, `down -v --remove-orphans` removeu containers, redes e volumes de
  prova.
- Nenhum código Python mudou. Verificação local final em `41df005`:
  `python -m pytest -q` → **2.186 aprovados, 17 ignorados, 2 avisos**;
  `npm test` → **243 aprovados**; `npm run build` → Vite 8.2.4 aprovado;
  `docker compose -f compose.postgres.yaml config --quiet` e o perfil `test` do
  Compose base também foram validados.

## Limites

Este stack é **local**, não produção: `trust` na rede interna, porta apenas em
`127.0.0.1`, sem TLS, PITR, backup offsite, retenção, restauração automatizada,
múltiplas réplicas ou failover. O dump de 106 KiB prova o caminho de backup
local, não uma política de recuperação. As Issues #4 e #5 permanecem abertas.
