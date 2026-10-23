<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Consumidores de execução física e catálogo do ObrasGov

Lote de 23/10/2026 (código deste lote: `4f92f89`).

## O que mudou

- Duas rotas reviewer-only em `/api/workbench/obrasgov/projeto/{project_id}`:
  - `/execucao`: linhas publicadas de execução física de um projeto
    (`execution_id`, `percentage_published`, datas, instrumento, payload e
    fonte);
  - `/catalogo`: linhas publicadas do projeto em qualquer um dos quatro
    datasets (`contrato`, `empenho`, `geometria`, `projeto-investimento`), com
    `dataset` opcional.- Nenhum projeto é vinculado a lugar, município ou obra endereçada; nenhuma
  porcentagem, fase ou valor é somado. 404 significa **nenhuma linha
  importada com esse id**, nunca obra inexistente. 400 para dataset
  desconhecido; 401 sem revisor autenticado.
- Sem nova migração: `obrasgov_execution` e `obrasgov_catalog` já estão no
  baseline `61fafa6c5eb1`.
- Evidência real (23/10/2026, bounded, não cobertura nacional):
  - `/obras/execucao-fisica` página 1: 200 linhas de **74.280** declaradas em
    372 páginas; import: **187 criadas, 5 iguais, 8 rejeitadas** por
    `percentual_execucao_fisica` inválido (nunca inventadas). SHA-256 da
    página `6674be39…ed105f`, 106.232 bytes.
  - `/obras/projeto-investimento` página 1: 200 linhas de **154.800**
    declaradas em 774 páginas; import: **200 criadas**. SHA-256
    `86e07c84…54249a2`, 445.951 bytes; frescura declarada `2026-10-23T00:00:00`
    com SHA-256 `f0d0df3e…6be1341`.
  - Rota de execução em projeto real `101695.29-99` retornou 1 linha com
    `percentage_published: 34.08`; rota de catálogo em projeto real
    `100920.42-84` retornou o projeto `PRO-CIDADES` de Urupema/SC. Recibo em
    [`../../reports/20261023-obrasgov-consumers.json`](../../reports/20261023-obrasgov-consumers.json).

## Evidência

- `test_resource_relations.py`: linhas exatas, filtro de dataset, 400/404/401
  e uso real de amostra bounded no banco sintético.
- Suíte integral: **2.206 aprovados, 17 ignorados, zero falhas**.

## Limites

As duas páginas são amostras de 372 e 774 páginas declaradas e **não** são o
Brasil. Um projeto ausente dessas páginas está fora da amostra, não fora do
país. `national_catalog_certified` continua `false`.
