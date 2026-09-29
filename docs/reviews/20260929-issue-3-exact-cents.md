# Centavos exatos no domínio compartilhado

Refs #3. Base: `f95c43955d95b2bf800535729f9b5f8099f4bd5b`.

Com precisão Decimal 3, a base convertia R$ 1.234,56 para 123000 centavos, em vez de 123456. Multiplicar antes de conferir integralidade também ocultava frações de centavo por arredondamento.

A conversão usa sinal, coeficiente e expoente com inteiros. Não depende de precisão/arredondamento/traps de operações Decimal. Preserva estornos, notação científica e zeros insignificantes; recusa floats e booleanos, não finitos e frações de centavo. Limite defensivo de 4096 dígitos no resultado evita expansão patológica de expoentes; não é teto financeiro de negócio.

## Evidência suplementar

70 novos casos coletados, incluindo 500 tuplas pseudoaleatórias comparadas com oráculo independente Fraction e propagação ao extrator documental. Fatia isolada: 153 aprovados (70 novos + 83 existentes). Quatro fatias combinadas reexecutadas: 230 aprovados.

Python 3.13.5/pytest 9.0.2 auxiliares; não substituem Python 3.14.7 e a suíte integral. Frontend, PostgreSQL, corpus oficial e deploy não foram executados. Estado remoto da CI deve ser conferido no PR.

```sh
python -m pytest backend/tests/test_money_exact_context.py backend/tests/test_domain.py backend/tests/test_documents.py backend/tests/test_backup.py -q
```

O PR #7 trata do normalizador Transferegov. Esta fatia corrige `bdt.domain` compartilhado, sem substituir o trabalho do normalizador. Não mistura fases, não altera schema e não migra valores já gravados. Auditoria histórica e reconciliação integral permanecem pendentes.

Referência: https://docs.python.org/3/library/decimal.html (contexto, Decimal.as_tuple).
