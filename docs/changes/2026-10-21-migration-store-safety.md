<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Correções de alvo de migração e segurança do store

Lote de 21/10/2026. Base de integração no `main`: `8bc4946`. Código em
`04e6aff`.

## O que mudou

- `bdt.migrate --database` agora vence uma variável `BDT_DATABASE_URL` herdada.
  Antes, o `env.py` consultava o ambiente primeiro e podia executar `upgrade`,
  `stamp` ou `check` no banco errado. Há teste de regressão com as duas URLs.
- `private_store_admin prune --apply` recusa um banco sem nenhuma referência.
  Isso impede que uma base vazia/errada transforme o store inteiro em “órfão” e
  apague todos os arquivos. O dry-run continua disponível para inspeção.
- `private_store.store_file` não apaga o próprio target quando a origem já é o
  caminho content-addressed.
- `alembic==1.20.0` passou a constar também dos extras `test` e `postgres`, para
  que `.[test]`, `.[test,postgres]` e `.[postgres]` consigam importar
  `bdt.migrate` e rodar os testes de migração.
- O healthcheck do PostgreSQL local usa TCP (`-h 127.0.0.1`) e `start_period`,
  evitando considerar saudável o servidor temporário de inicialização.
- `docker-compose.postgres.yml` é o ponto de entrada de compatibilidade para o
  stack durável; `docker compose -f docker-compose.postgres.yml up --build -d`
  sobe o mesmo conjunto de `compose.postgres.yaml`.

## Evidência local

- Suíte Python integral em `04e6aff`: **2.189 aprovados, 17 ignorados, zero
  falhas** (6m41s). Dois avisos não bloqueantes.
- Recorte de migração/store/PNCP/originais: **38 aprovados**.
- O teste de precedência confirma que `--database` cria o banco solicitado e
  não cria o banco apontado pela variável de ambiente.
- O teste de prune confirma que `--apply` falha e preserva o arquivo quando não
  há referências.
- `docker compose -f docker-compose.postgres.yml up -d` subiu
  `postgres`, `migrate` e `app`; app ficou healthy e `/api/health` respondeu
  `{"status":"ok","version":"0.1.0","llm_required":false}`. O stack e os
  volumes foram removidos com `down -v`.
- Lock Linux continua com 51 pacotes; o manifesto foi reemitido com o novo hash
  do `pyproject.toml`.

## Limites

O stack continua local: autenticação `trust` na rede interna, `bdt_admin`
superusuário acessível aos containers dessa rede, sem TLS/PITR/offsite,
restauração automatizada ou multi-réplica. A correção de prune é uma guarda
contra base errada, não uma política de retenção. Issues #4 e #5 permanecem
abertas.
