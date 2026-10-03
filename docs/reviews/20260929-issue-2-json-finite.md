# JSON: rejeitar overflow no parser padrão

Refs #2. Base: `f95c43955d95b2bf800535729f9b5f8099f4bd5b`.

`parse_constant` recusa os literais NaN/Infinity, mas não recebe números válidos em JSON cujo expoente ultrapassa o intervalo de float. O novo parser padrão recusa resultados não finitos com `non_finite_json_number`. O parser explícito Decimal continua preservando precisão e expoentes grandes finitos; chaves duplicadas continuam proibidas.

## Validação local suplementar

12 novos testes: overflow positivo/negativo/na fronteira IEEE, objetos aninhados, constantes não finitas, Decimal explícito, coordenadas, inteiros e chaves duplicadas. A fatia isolada passou com 95 testes (12 novos + 83 de regressão); as quatro fatias combinadas foram reexecutadas com 230 aprovados em 29/09/2026.

Ambiente auxiliar: Python 3.13.5, pytest 9.0.2. Não substitui a suíte integral no Python 3.14.7 exigido pelo projeto. PostgreSQL, frontend, corpus oficial e deploy não foram executados. O resultado remoto deve ser consultado no PR, não inferido desta nota.

```sh
python -m pytest backend/tests/test_json_numeric_boundary.py backend/tests/test_domain.py backend/tests/test_documents.py backend/tests/test_backup.py -q
```

Não certifica ingestão nacional, não muda denominadores e não realiza coleta externa. A issue ampla permanece aberta. Mudança complementar à validação de paginação do PR #8, sem editar seus arquivos.

Referência primária: https://docs.python.org/3/library/json.html (parse_float e parse_constant).
