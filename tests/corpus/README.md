<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Corpus de validação documental

## O que está sendo preservado

`ocr-reviewed/` contém os **quatro arquivos originais** do artefato
`portuguese-ocr-synthetic-evidence` (execução 34008123457, artefato 9981605829),
mais um manifesto e duas representações de extração verificáveis. Os PDFs são
sintéticos, gerados pelo projeto para testar o pipeline. **Não são convênios,
planos de trabalho ou documentos oficiais.** Não entram no catálogo público.

O teste original executou Tesseract em português sobre uma página digitalizada.
A preservação não executa o OCR outra vez: conserva sua saída, verifica os bytes,
refaz apenas a extração nativa e compara os quatro candidatos conhecidos.
O arquivo `recognized-text.txt` é a saída do motor daquela execução, não uma
transcrição humana de um documento oficial. `native-extraction.json` contém a
extração nativa e posições; `result.json` é preservado sem modificação.

O manifesto registra IDs de origem, revisão, tamanho e SHA-256 de cada arquivo.
Os exemplos usam referências fictícias para teste; não demonstram um vínculo
entre instituições reais, pagamento, capacidade atual ou existência de vagas.
Os materiais originais gerados pelo projeto nesta pasta usam CC-BY-4.0. O código
do verificador segue a licença do software; isso não relicencia fontes externas.

## Verificação e recuperação

Com Python 3.14.7 e dependências do projeto instaladas:

```sh
python ops/archive_ocr_evidence.py verify tests/corpus/ocr-reviewed
```

O workflow `Preserve reviewed OCR evidence` recupera apenas o artefato indicado,
recusa arquivos adicionais ou alterados, verifica a extração e publica somente
essa pasta. Nunca lê o banco de usuários nem o armazenamento documental privado.
A execução deve terminar com sucesso antes de afirmar que os arquivos estão no
histórico do repositório. Artefatos temporários de CI não substituem esse arquivo.

## Documentos de outras fontes

Os documentos oficiais e as imagens de terceiros exigem inventário próprio:
origem, data, hash, autorização de redistribuição, exame de dados pessoais e
registro separado de cada derivado. Um URL público ou um resultado de OCR não é,
sozinho, permissão de republicação. Não serão copiados automaticamente os bancos
locais, relatórios de contas, fotos de cidadãos ou PDFs ainda não inspecionados.
Os pacotes iniciais de planejamento contêm excertos transcritos; esses excertos
não substituem os originais oficiais nem uma avaliação anotada de OCR.
