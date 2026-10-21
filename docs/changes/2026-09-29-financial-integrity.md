<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Integridade financeira Transferegov — Issue #3

A conversão para centavos usa somente texto e aritmética inteira: não depende da
precisão ou dos traps do contexto global `Decimal`. Floats binários e booleanos
são recusados; CSVs continuam fornecendo strings. Valores negativos de aditivos,
centavos e os formatos brasileiros já aceitos permanecem preservados.

Datas declaradas passam por validação de calendário. Uma data presente e
inválida não pode ser substituída silenciosamente pelo ano. O fallback de ano
só ocorre quando a data está ausente; seu formato de saída legado é preservado
e não constitui prova de um dia de assinatura. Os normalizadores existentes
continuam excluindo registros com data ou valor inválido, sem fabricar eventos.

Uma mesma chave `NR_CONVENIO` com município ou proponente divergentes interrompe
a construção do crosswalk com `conflicting_municipality_crosswalk`, em qualquer
ordem de entrada. A comparação usa o nome completo antes da projeção limitada
para exibição. Repetições exatas e aliases territoriais do lookup revisado
continuam idempotentes. Os arquivos originais não são reescritos; a divergência
exige reconciliação pelo operador, não escolha da última linha ou fuzzy match.

Regressões: `backend/tests/test_transferegov_finance_integrity.py`.
Vinte e um casos reproduziram falhas na revisão-base
`f95c43955d95b2bf800535729f9b5f8099f4bd5b`.
Comando: `python -m pytest backend/tests/test_transferegov_finance.py backend/tests/test_transferegov_finance_integrity.py`.

Nenhum dado oficial foi reimportado nesta alteração. As fases financeiras não
são somadas, conflitos de versões financeiras continuam preservados e os demais
módulos/fontes e a reconciliação integral da Issue #3 permanecem abertos.
