<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Conector e consumidor de empenhos de Parcerias

Lote de 22/10/2026. Código em `8ba31e022eea7d88d14d6d66a33c8e936c1ae9e7`.

## O que mudou

- Novo conector `python -m bdt.transferegov_parceria_empenhos collect|import`
  para `/parcerias/empenho-parceria`, com página, URL, bytes, SHA-256 e
  manifesto.
- Import idempotente por `id_empenho_parceria`; valores ficam como publicados e
  nunca são somados.
- Consumidor `GET /api/workbench/parcerias/{id_parceria}/empenhos` somente para
  revisor, com paginação, `aggregate: null` e linhas exatas.
- Migração `0003_parceria_empenhos`; 43 tabelas de runtime.
- Evidência real: 200 linhas de **69.345** empenhos declarados em 347 páginas;
  página de 173.109 bytes, SHA-256 `12badc1f…f5352c`; parceria 14487 com um
  empenho de R$ 1.600.000,00 publicado. Recibo em
  `reports/20261022-transferegov-parceria-empenhos.json`.

## Evidência

- `test_transferegov_parceria_empenhos.py`: coleta bounded, import idempotente
  e recusa de pasta reutilizada.
- `test_resource_relations.py`: consumidor de empenhos de parceria e ausência
  de total.
- `test_migrations.py`: head `0003_parceria_empenhos` e `check`
  sem deriva.
- Suíte integral: **2.204 aprovados, 17 ignorados, zero falhas**.

## Limites

Uma página de 347 não é o Brasil. Empenho é compromisso orçamentário, não
pagamento; o favorecido é o publicado, sem inferência. A rota é privada de
revisão, não release público. `national_catalog_certified` continua `false`.
