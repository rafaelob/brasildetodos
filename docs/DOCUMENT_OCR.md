<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# OCR privado de páginas selecionadas

A extração nativa de `bdt.document_job` vem primeiro. A rotina `bdt.document_ocr`
exige documento já registrado e inspecionado, revisor existente, original local
com o mesmo SHA-256 e páginas explicitamente selecionadas. Não baixa arquivos,
não publica texto nem altera o original. Nenhum LLM é necessário.

```sh
python -m bdt.document_ocr --database sqlite:///data/bdt.db \
  --document ID_DO_DOCUMENTO --operator NOME_DO_REVISOR \
  --path /originais/documento.pdf --pages 2 5 --language por
```

Instale Poppler, Tesseract e `tesseract-ocr-por` no worker isolado. O processo deve
rodar sem acesso externo à rede, com limites do sistema operacional e sem
credenciais desnecessárias. Limites por comando: 32 MiB, dez páginas, 1..300
segundos por etapa de renderização/reconhecimento e texto de até 200 mil caracteres
por página. A rotina não é um endpoint público e não deve ser exposta como tal.

Somente páginas classificadas como `ocr_candidate` ou `review_encoding` entram
no comando. Página nativa é recusada, não rasterizada por conveniência. Texto
nativo e palavras/posições anteriores permanecem intactos. O resultado adicional
fica em `ocr_candidate_text`, acompanhado de idioma, página e hash original;
`ocr_candidates` contém apenas sugestões, nunca fatos publicados automaticamente.

## Concorrência e recuperação

Um token de processamento é obtido atomicamente. Enquanto ele existir, outro
processo de OCR para o mesmo documento é recusado. Todas as páginas selecionadas
são gravadas juntas, ou nenhuma: erro, mudança do original, revogação do operador
ou perda do token impedem a gravação. O log guarda tipo de erro, nunca saída
arbitrária do motor ou texto integral do documento.

Se o processo for encerrado pelo sistema operacional e deixar um token, primeiro
confirme que o worker foi interrompido. Um revisor pode então executar:

```sh
python -m bdt.document_ocr --database sqlite:///data/bdt.db \
  --document ID_DO_DOCUMENTO --operator NOME_DO_REVISOR \
  --recover-lease ocr_TOKEN_EXATO_DE_12_CARACTERES_HEXADECIMAIS
```

A recuperação exige igualdade do token, não um reset genérico. Uma execução antiga
que tente gravar depois da recuperação não consegue sobrescrever a extração nova.

## Revisão e evidências

O workbench existente lê o texto reconhecido e permite uma proposta de vínculo
com trecho literal. A revisão independente e o aceite de publicação de trechos
continuam obrigatórios. OCR pode errar números, datas e nomes; correspondência
literal não comprova a verdade nem a autenticidade do documento.

A suíte unitária usa motor substituto para testar 28 comportamentos, sem executar
OCR repetido. A workflow `Local Portuguese OCR integration` executa uma única
página digitalizada sintética com Tesseract em português e confere quatro campos,
privacidade e preservação do original. Essa prova não substitui avaliação por
campo em corpus oficial digitalizado, nem representa qualidade medida no Brasil.
