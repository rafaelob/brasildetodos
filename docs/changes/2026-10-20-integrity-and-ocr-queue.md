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
- Correção de compatibilidade do fingerprint: lugares e recursos publicados antes
  da ampliação do contrato não tinham as chaves opcionais, enquanto o payload novo
  as serializava como `null`. O fingerprint de lugares e a comparação de `Source`
  de recursos agora ignoram somente chaves opcionais ausentes; valores presentes
  continuam participando do hash. Um teste cobre linhas legadas.
- O teste de navegador do mapa deixou de usar `page.wait_for_function` com string,
  que era bloqueado por `script-src 'self'`, e passou a usar expectativas de
  locator. A política de segurança continua sem `unsafe-eval` e sem `bypass_csp`.
- Os aceites `Public catalog API acceptance` e `Combined public resource release`
  deixaram de depender de artifacts expirados: baixam o ZIP imutável da release,
  conferem tamanho e SHA-256 contra `data/releases/*.json` e executam a instalação
  e a consulta sobre esses bytes. Os dois aceites passaram localmente sobre o ZIP
  publicado: 96.123 lugares e 6.679 recursos, com replay idempotente.
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

Código testado: `59a02f2bdabefdbeeac4e1f757a903084d9525ef`. Esta nota foi
atualizada em commit documental posterior; nenhum código mudou depois da suíte.

Python **3.14.8** (`.venv`), Node.js **24.20.0**.

- Catálogo, instalação nacional, bundle público e release escolar: **110
  aprovados, 3 ignorados**.
- Suíte Python integral: **2.138 aprovados, 17 ignorados, zero falhas**.
- Web: **243 aprovados, zero falhas**, e build TypeScript/Vite aprovado.
- `npm audit --audit-level=high`: **0 vulnerabilidades**.
- `python -m compileall -q backend ops` e
  `git -c core.whitespace=cr-at-eol diff --check`: aprovados.

## Releases publicados reverificados

Os dois pacotes publicados foram baixados do GitHub Releases e verificados com o
código deste lote. Os recibos ficaram fora do repositório; os valores abaixo são
os resultados registrados.

- `public-data-20260906-v1`: `public-data.zip` com 28.096.042 bytes e SHA-256
  `6d62f9ca107f3672e8dcfb0a7d0b591010931d9daa05eaf6212c91c3cecc1639`.
  Resultado `status: passed`: 96.123 lugares, 6.679 recursos e 6.679 revisões,
  0 eventos financeiros, 0 usuários e 0 observações; API consultada, rotas
  privadas protegidas, banco existente não modificado e nenhum registro sintético
  adicionado. `public_deployment` permaneceu **falso**. O mesmo ZIP passou nos
  aceites de catálogo público e de recursos combinados: 6.679 revisões, 55
  registros com valores subcent, replay idempotente e 0 eventos financeiros.
- `education-2025-20260907-v1`: `education-catalog.zip` com 23.807.757 bytes e
  SHA-256 `483bba3a2e71d5360061cbc1880b41c8ab4915e94199a74bb8ac5678ee5fcfe7`.
  Resultado `status: passed`: 214.192 registros lidos, 138.086 elegíveis, 76.106
  excluídos, 0 geometria e 27 UFs; API consultada. `browser_checked` permaneceu
  **falso**, `public_deployment` **falso** e `national_completeness_certified`
  **falso**.

Essas verificações comprovam a instalação e a consulta dos bytes publicados, não
cobertura nacional, navegador real nem deploy público.

## Limites

As provas usam SQLite isolado e registros sintéticos. Não houve ingestão de dados
oficiais, avaliação de corpus oficial de OCR, execução de navegador nesta rodada,
PostgreSQL durável, migração Alembic, backup de produção ou deploy público.
`national_catalog_certified` continua **falso**. As Issues #2–#5 permanecem
abertas; este lote reduz lacunas de software, mas não certifica cobertura nacional
nem operação em produção.
