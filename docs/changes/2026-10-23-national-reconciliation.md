<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Reconciliação instalado vs declarado do banco nacional

Lote de 23/10/2026 (código deste lote: `d6c26a6`).

## O que mudou

- `ops/national_reconciliation.py`: leitura de somente leitura de
  `data/national.db` + `reports/20261021-national-data.json` para comparar o
  que está **instalado** com o que foi **declarado** pelas duas coletas frescas
  de 21/10/2026 (CNES/INEP), tudo com URL e SHA-256 registrados.
- `reports/20261023-national-reconciliation.json` — recibo do run de 23/10:
  - saúde: **96.123 instalados / 96.607 declarados** → gap **−484** (banco
    histórico vs coleta fresca; gap real esperado até a edição reconciliada);
  - escolas: **138.086 instaladas / 138.086 declaradas** → gap **0** (igualdade
    aritmética com o total declarado; **não** prova fusão ou reprodução);
  - contagem por UF das 27 UFs presentes;
  - `without_geometry` 138.093 (138.086 escolas + 7 outros);
  - `national_catalog_certified` **false** e `not_national_coverage` true.
- Denominador ausente nunca é inventado: se o recibo da fonte não publicar
  `eligible`, a fonte entra como `missing_denominator` e sem gap.
- Quatro testes sintéticos + run real de 23/10/2026:

```bash
# teste: pytest backend/tests/test_national_reconciliation.py
# run real: python ops/national_reconciliation.py
```

## Evidência

- `test_national_reconciliation.py`: gap exato (health −2 e school 0),
  denominador `None` nunca convertido em valor, recibo com shape alterado é
  recusado (`receipt_schema_changed`), CLI escreve o relatório explicitamente.
- Suíte integral: **2.210 aprovados, 17 ignorados, zero falhas**.

## Limites

Os dois lados do gap são de fontes separadas: o banco é uma release
**histórica** e a coleta CNES é **fresca** de 21/10/2026. O gap de saúde de
**−484** é a diferença entre essas duas linhas de tempo, **não** uma perda. Sair
de gap zero para certificação exige: (a) base de UNH/Nacional com denominador
por UF e por município; (b) união da edição instalada com as coletas frescas; (c)
decisão publicada sobre competência/revisita.
