# Extração: preservar identificadores completos

Refs #4. Base: `f95c43955d95b2bf800535729f9b5f8099f4bd5b`.

A base extraía 12/2025 de CONTRATO 12/20255 e reconhecia CONTRATO dentro de SUBCONTRATO. Limites lexicais passam a recusar truncamentos em convênio, proposta, contrato, aditivo, processo, CNPJ numérico e referência legal. Pontuação válida e offsets da fonte são preservados.

A mudança é conservadora: não promete cobertura de formatos alfanuméricos ou de um corpus oficial. Resultados permanecem `state=candidate`, `publication_allowed=false`. Não executa OCR externo, não muda originais e não permite publicação automática. Complementa o PR #6, que trata da revisão/publicação de evidências, em outro módulo.

## Validação suplementar

52 casos novos: identificadores truncados, rótulos embutidos em palavras maiores, limites de CNPJ, pontuação e preservação de raw/start/end. Fatia isolada: 135 aprovados (52 novos + 83 existentes). Quatro fatias combinadas reexecutadas: 230 aprovados.

Python 3.13.5/pytest 9.0.2 auxiliares; Python 3.14.7 obrigatório preservado. Suíte integral, CI remoto, frontend, PostgreSQL e corpus oficial não comprovados por estes testes. Estado remoto deve ser consultado no PR.

```sh
python -m pytest backend/tests/test_document_candidate_boundaries.py backend/tests/test_domain.py backend/tests/test_documents.py backend/tests/test_backup.py -q
```

Fila persistente, editor, avaliação por campo e roteamento OCR continuam pendentes na issue ampla.

Referência: https://docs.python.org/3/library/re.html (lookaround e limites lexicais).
