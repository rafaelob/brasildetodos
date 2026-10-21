<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Integridade das fatias #2–#5 e fila OCR operacional

Lote de 20/10/2026. Base de integração no `main`: `8434d0b`.
As nove fatias corretivas que estavam em branches separadas foram integradas
por merge local, sem force push e sem reescrever o histórico publicado.

## O que foi integrado

- `fix/2-paginated-collection-integrity`, `fix/3-transferegov-financial-integrity`,
  `fix/4-documentary-evidence-integrity` e `fix/5-atomic-schema-initialization`.
- `fix/issue-2-import-status-timezones-20261015`, `fix/issue-2-json-finite-20260929`,
  `fix/issue-3-exact-cents-20260929`, `fix/issue-4-document-boundaries-20260929`
  e `fix/issue-5-backup-safety-20260929`.
- Fila OCR persistente e privada: `enqueue`, `claim` com lease, `complete`,
  `fail`/retry, cancelamento, reap de lease expirado, retenção e CLI de operador.
  A fila não guarda bytes nem texto extraído; o trabalhador apresenta o original
  e o SHA-256 é conferido novamente antes do reconhecimento.
- Rotas de revisão em `/api/workbench/ocr/jobs`, com autenticação de revisor,
  limite de taxa e nenhuma publicação automática. O Workbench mostra a fila e
  permite enfileirar, cancelar e repetir; pt-BR, en e es foram atualizados.
- Contrato de `Source` com edição, dicionário, licença e data de publicação
  opcionais. Quando presentes, os campos são coerentes e entram no manifesto do
  catálogo; quando ausentes, nada é inventado e releases legados continuam válidos.
- Manifesto de catálogo com `municipal_partitions` por fonte/UF/município:
  `read`, `accepted`, `excluded`, `invalid`, geometria e períodos de referência.
  A verificação e a instalação recusam partições adulteradas.
- `/api/coverage` mantém registros excluídos visíveis e separa `read`, `accepted`
  e `excluded`; somente aceitos contam como lugares carregados. UF com apenas
  registros excluídos não é contada como cobertura.
- `/api/places` aceita `has_geometry=true|false`; pares de coordenadas incompletos
  não são tratados como geometria válida.
- A leitura de página do Workbench valida o pacote de extração e devolve 409 para
  pacote corrompido, em vez de servir uma página não verificada.
- A revisão de vínculo persiste `public_excerpt_checked` no evento de auditoria.
- Vite foi atualizado de 8.2.2 para 8.2.4 e o lock web foi corrigido; a CI passa a
  falhar com `npm audit --audit-level=high`.
- O checkout passou a preservar os bytes exatos de `pyproject.toml`, do lock Linux
  e do corpus OCR versionado. Sem isso, `core.autocrlf=true` no Windows alterava
  os arquivos e quebrava os testes de manifesto e de corpus.

## Evidência local

Python **3.14.8** (`.venv`), Node.js **24.20.0**.

- Fatias corretivas focadas: **276 aprovados, 5 ignorados**.
- Fila OCR, catálogo, cobertura, API, domínio, lock e corpus: **224 aprovados,
  1 ignorado**.
- Suíte Python integral: **2.136 aprovados, 17 ignorados, zero falhas**.
- Web: **243 aprovados, zero falhas**, e build TypeScript/Vite aprovado.
- `npm audit --audit-level=high`: **0 vulnerabilidades**.
- `python -m compileall -q backend ops` e `git diff --check`: aprovados.

## Limites

As provas usam SQLite isolado e registros sintéticos. Não houve ingestão de dados
oficiais, avaliação de corpus oficial de OCR, execução de navegador nesta rodada,
PostgreSQL durável, migração Alembic, backup de produção ou deploy público.
`national_catalog_certified` continua **falso**. As Issues #2–#5 permanecem
abertas; este lote reduz lacunas de software, mas não certifica cobertura nacional
nem operação em produção.
