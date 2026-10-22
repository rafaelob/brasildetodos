<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Consumidores de empenhos especiais e PDDE

Lote de 22/10/2026. Base de integração no `main`: `c8adc5d`. Código em
`1c28b551d5ce9dfc5d12feac1161a940e7561be6`.

## O que mudou

- `GET /api/workbench/resources/{resource_id}/empenhos` consome, para revisor
  autenticado, as linhas de `transferegov_especiais_empenhos` cujo
  `id_plano_acao` é exatamente o `source.record_id` do recurso
  `transferegov_special_plans`.
- `GET /api/workbench/places/{place_id}/pdde` consome as linhas de
  `pdde_payments` cujo `school_place_id` é exatamente a escola.
- Ambas paginam (`page`, `limit` até 200), retornam linhas publicadas exatas,
  `total_rows` apenas como contagem e `aggregate: null`; não existe campo de
  soma monetária, rateio, destinatário inferido ou vínculo institucional.
- As tabelas aditivas são criadas no startup sem alterar o release público.
- O coletor de empenhos especiais foi exercitado contra a API pública:
  200 linhas criadas de 61.485 itens declarados em uma página bounded; o plano
  31089 retornou duas linhas pela rota.
- `reports/20261022-transferegov-special-empenhos.json` registra URL, SHA-256,
  bytes, contagens e o exemplo real; não contém dados pessoais.

## Evidência

- `backend/tests/test_resource_relations.py`: 3 aprovados; cobre plano exato,
  outro plano excluído, paginação, ausência de total, 401 anônimo e 404.
- Suíte integral: **2.196 aprovados, 17 ignorados, zero falhas**.
- Web não mudou; o último build Vite 8.2.4 e os 243 testes web continuam a
  referência.

## Limites

A coleta de empenhos é uma página, não o Brasil. O PDDE foi testado com fixture
sintética, não com um arquivo nacional novo. Empenho não é pagamento; receptor
do PDDE é unidade executora/entidade, não prova de repasse à escola. As rotas
são de revisão, não um release público; `national_catalog_certified` continua
`false`.
