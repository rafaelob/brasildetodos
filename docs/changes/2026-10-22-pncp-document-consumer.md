<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Consumidor de documentos PNCP por contrato

Lote de 22/10/2026. Código em `79beb48191645a50b31aa118825422dffa43a5b8`.

## O que mudou

- `GET /api/workbench/resources/{resource_id}/documentos` exige revisor,
  identifica um `Resource` de `pncp_contracts`, lê `cnpj`, ano e sequencial do
  `source.record_id` e lista os metadados de `pncp_contract_documents`.
- A resposta inclui título, tipo, data, URL oficial, SHA-256, tamanho, status,
  revisão e datas de primeira/última visão; **não** inclui bytes, conteúdo ou
  link público. `publication_allowed` permanece `false` e `review_required`
  permanece `true`.
- Paginação até 200; tabelas de documentos são criadas de forma aditiva no
  startup, sem alterar o release público.
- O coletor real foi exercitado no contrato
  `00000368000150-2-000207/2026`: um documento de **87.356 bytes**, SHA-256
  `b5f50396…b8d9bd`, status `present`, retornado pela rota sem bytes.
- Recibo: `reports/20261022-pncp-document-consumer.json`.

## Evidência

- `backend/tests/test_resource_relations.py`: 5 aprovados; cobre plano,
  paginação, PDDE, contrato PNCP, não-contrato e ausência de conteúdo.
- Suíte integral: **2.198 aprovados, 17 ignorados, zero falhas**.
- Documento real coletado com uma página, status `complete`, `not_listed=0`.

## Limites

Um contrato e um documento não são um censo nacional. O consumidor expõe
metadados e hash, não o PDF; não há OCR, ground truth por campo, vínculo
institucional ou publicação automática. O corpus OCR oficial e o editor de
revisão continuam pendentes na Issue #4.
