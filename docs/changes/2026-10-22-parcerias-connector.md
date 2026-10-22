<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Conector e consumidor de Parcerias do Transferegov

Lote de 22/10/2026. Código em `2bfb4129e50ffe7c07cf9219ffbe3f4487b819b9`.

## O que mudou

- Novo conector `python -m bdt.transferegov_parcerias collect|import` para o
  endpoint oficial `/parcerias/parceria`, com página, URL, bytes, SHA-256 e
  manifesto `collection.json`.
- Import idempotente por `id_parceria`, preservando o payload publicado e a
  fonte; a tabela é criada pela migração **`0002_transferegov_parcerias`**.
- Consumidor `GET /api/workbench/parcerias/{id_parceria}` somente para revisor:
  devolve o cabeçalho exato, `publication_allowed=false` e
  `review_required=true`; sem soma, pagamento, vínculo territorial ou release
  público.
- Evidência real: 200 linhas criadas de **89.695** parcerias declaradas em 449
  páginas; página de 132.765 bytes com SHA-256
  `bbc989c7…6d01e14`; amostra `id_parceria=37840`, situação `Aprovada`.
- Recibo: `reports/20261022-transferegov-parcerias.json`.

## Evidência

- `backend/tests/test_transferegov_parcerias.py`: coleta bounded, import
  idempotente e recusa de pasta reutilizada.
- `backend/tests/test_resource_relations.py`: consumidor de parceria e 404.
- `test_migrations.py`: upgrade até `0002_transferegov_parcerias`, `check` sem
  deriva e 42 tabelas de runtime.
- Suíte integral: **2.201 aprovados, 17 ignorados, zero falhas**.

## Limites

Uma página de 449 não é o Brasil. A rota não prova execução, pagamento ou
vínculo com escola/obra. O endpoint não é publicado como release; os bytes e
payloads ficam locais. `national_catalog_certified` continua `false`.
