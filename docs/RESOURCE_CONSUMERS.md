<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Consumidores de recursos oficiais

Rotas **somente para revisor autenticado** que leem linhas oficiais já
importadas. Elas não publicam automaticamente, não criam vínculo com escola,
obra ou município e não calculam total monetário. Um empenho não é pagamento.

## Empenhos de um plano especial

```http
GET /api/workbench/resources/transferegov_special_plans%3A31089/empenhos?page=1&limit=50
```

A rota exige `Resource.id` de um recurso cujo `source.dataset` seja
`transferegov_special_plans` e cujo `source.record_id` seja o
`id_plano_acao`. Retorna apenas as linhas cujo `id_plano_acao` é exatamente
esse, com:

- `empenho_id`, `numero_empenho`, `situacao`, `descricao_situacao`,
  `data_emissao`;
- `valor_empenho_publicado` exatamente como veio na origem;
- UG responsável/emitente, fonte, plano interno e `id_plano_acao`;
- `source` com URL, SHA-256 e data de coleta;
- `page`, `limit`, `total_rows` (contagem de linhas, não de dinheiro) e
  `has_more`;
- `aggregate: null` e nenhum campo `total`/`sum` monetário.

`limit` máximo é 200. Recurso inexistente, não-plano ou plano inexistente
retorna 404; sessão ausente/não revisora retorna 401/403.

## Cabeçalho de parceria Transferegov

```http
GET /api/workbench/parcerias/37840
```

A rota exige revisor e devolve o cabeçalho exato já importado pelo conector
bounded `transferegov_parcerias`. O payload inclui os campos publicados, a
situação e a fonte com URL/SHA-256; `publication_allowed=false` e
`review_required=true`. Não há soma, pagamento, vínculo com escola/obra ou
cobertura nacional. A amostra real de 200 parcerias de 89.695 declaradas está
em [`reports/20261022-transferegov-parcerias.json`](../reports/20261022-transferegov-parcerias.json).

## Documentos de um contrato PNCP

```http
GET /api/workbench/resources/pncp_contracts%3A00000368000150-2-000207%2F2026/documentos?page=1&limit=50
```

A rota exige um `Resource` cujo `source.dataset` seja `pncp_contracts`, lê o
`cnpj`, ano e sequencial do `source.record_id` e retorna os metadados dos
documentos oficiais já coletados. Não devolve bytes nem conteúdo; inclui
SHA-256, tamanho, título, tipo, status, revisão, URL oficial e
`publication_allowed: false`/`review_required: true`. O PDF permanece no
armazenamento privado. Uma amostra real de um contrato e um documento de
87.356 bytes está em
[`reports/20261022-pncp-document-consumer.json`](../reports/20261022-pncp-document-consumer.json).

## PDDE por escola

```http
GET /api/workbench/places/test%3Aschool/pdde?page=1&limit=50
```

A rota exige um `Place` do tipo `school` e retorna as linhas cujo
`school_place_id` é exatamente o `place_id`. Os `values` são o texto publicado;
não há soma. O `recipient_name` é a unidade executora/entidade, **não prova** de
que o dinheiro chegou à escola. A rota é validada com fixture sintética; não há
arquivo PDDE nacional novo neste lote.

## Evidência real

O coletor de empenhos especiais foi executado em 22/10/2026 com uma página
limite: 200 linhas criadas de 61.485 itens declarados, sem rejeição. O plano
31089 retornou duas linhas pela rota. O recibo agregado está em
[`reports/20261022-transferegov-special-empenhos.json`](../reports/20261022-transferegov-special-empenhos.json).

Isso é coleta **bounded**, não cobertura nacional. A rota não pertence ao
release público; é uma superfície de revisão. `national_catalog_certified`
continua `false`.

## Testes

```bash
python -m pytest backend/tests/test_resource_relations.py -q
```

Cobrem plano exato, exclusão de outro plano, paginação, ausência de agregado,
401 anônimo, 404 para não-plano, documentos PNCP sem bytes, parcerias e o
conector bounded. A suíte integral deste lote passou com **2.201 aprovados,
17 ignorados**.
