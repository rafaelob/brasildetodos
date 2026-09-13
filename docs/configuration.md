<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Configuração

`compose.yaml` é a fonte versionada do runtime local e dos perfis de teste. `docker-compose.yml`
é apenas o ponto de entrada de compatibilidade que inclui essa fonte; não repete valores.

## Itens de configuração

| Item | Fonte | Finalidade |
|---|---|---|
| `BDT_DATABASE_URL` | ambiente do processo; padrão local em `compose.yaml` | Seleciona o banco. O serviço local usa SQLite; produção exige uma URL PostgreSQL injetada por infraestrutura autorizada. |
| `BDT_PORT` | ambiente consumido por `compose.yaml` | Altera somente o bind local em `127.0.0.1`; o padrão é `8008`. |
| `BDT_PUBLIC_ORIGIN` e `BDT_ALLOWED_HOSTS` | ambiente consumido por `bdt.api` e valores locais em `compose.yaml` | Delimitam origem e host aceitos. Produção recusa origem sem HTTPS. |
| perfil Compose `test` | `compose.yaml` | Sobe PostgreSQL efêmero em `tmpfs` e rede interna, sem porta publicada, e conecta o runner pelo papel `bdt_ci` sem privilégios administrativos. |

Os nomes e limites operacionais das demais variáveis ficam em [Operação](OPERATIONS.md). Valores de
produção pertencem ao gerenciador de segredos da infraestrutura e não entram neste repositório.

## Registro de mudanças

| Data | Mudança e motivo | Reversão |
|---|---|---|
| 2026-09-12 | O perfil `test` passou a ser a única configuração local da prova PostgreSQL; o workflow usa o mesmo perfil para impedir deriva entre CI e Compose. | Reverter `compose.yaml`, `docker-compose.yml`, `ops/postgres-test-init.sql` e `.github/workflows/runtime-validation.yml` no mesmo commit; a aplicação local SQLite não precisa de migração ou remoção de volume. |
