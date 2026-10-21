<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Estrutura documental e campo do vínculo

Lote de 20/10/2026. Base de integração no `main`: `2e938d3`. O código deste
lote está em `7d849431b8a65316664cf244d2d5d227311f4893`.

## O que mudou

- `inspect_pdf` passou a usar `extractor_version: native-pdf-v2` e a registrar
  `document_family`, `multipage_tables`, orientação efetiva, fração de imagem,
  tamanho do texto e `ocr_eligible` por página.
- Famílias documentais são apenas marcadores lexicais de convênio, plano de
  trabalho, contrato e termo aditivo, com página e trecho de evidência. O
  resultado continua `review_required: true` e `publication_allowed: false`;
  não é classificação jurídica.
- Datas de assinatura, início, término, publicação e aditivo são candidatos
  separados. Datas brasileiras explícitas `dd/mm/yyyy` só viram ISO quando
  formam uma data válida; uma data impossível permanece visível com
  `date_valid: false`.
- Valores estimado, global, de aditivo, de parcela, pago e de contrapartida
  continuam candidatos em centavos, com papéis distintos. Nenhum valor é somado
  ou convertido em pagamento.
- Tabelas multipágina só são unidas quando páginas consecutivas repetem um
  cabeçalho idêntico. As linhas preservam o número da página; páginas com mais
  de uma tabela não são unidas automaticamente. O resultado continua um auxílio
  de revisão, não prova de completude.
- A orientação é derivada da rotação e das dimensões efetivas da página.
  Rotação fora de 0/90/180/270 vira `review_orientation`.
- Páginas com texto nativo e área de imagem relevante viram `hybrid_review` em
  vez de serem tratadas como nativas ou integralmente digitalizadas. A
  elegibilidade de OCR é explícita e compatível com extrações legadas.
- `Link.field` é opcional, limitado a campos conhecidos, preservado no payload
  público e privado e migrado como coluna nullable pelo mecanismo aditivo já
  existente. Bancos legados recebem a coluna sem perder linhas.
- O Workbench permite escolher o campo do trecho, mostra a família documental,
  as novas rotas e um aviso de que conferir a transcrição não confirma o vínculo
  institucional. As strings foram adicionadas em pt-BR, en e es.
- O corpus OCR sintético versionado foi rederivado com o novo extrator. Os PDFs
  originais e o texto reconhecido não foram alterados; o manifesto registra o
  novo hash de `native-extraction.json`. A verificação continua offline, sem
  OCR e sem rede.

## Evidência local

Python **3.14.8** (`.venv`) e Node.js **24.20.0**.

- Suíte Python integral: **2.147 aprovados, 17 ignorados, zero falhas**.
  A execução ocorreu sobre a mesma árvore de código que originou o commit
  `7d84943`; nenhuma alteração de código foi feita depois dela.
- Recorte documental/OCR/corpus: **93 aprovados**.
- Web: **243 aprovados, zero falhas**; build TypeScript/Vite 8.2.4 aprovado.
- `npm audit --audit-level=high`: **0 vulnerabilidades**.
- `python -m compileall -q backend ops` e
  `git -c core.whitespace=cr-at-eol diff --check`: aprovados.
- A suíte integral emitiu dois avisos não bloqueantes: depreciação de
  `anyio.abc.BlockingPortal` no TestClient e Operation ID duplicado para
  `/api/health`. Nenhum deles é falha de teste.

## Limites

Não houve avaliação com corpus oficial, armazenamento de originais, ingestão
nova de documentos oficiais, migração Alembic, PostgreSQL durável, backup de
produção ou deploy público. A classificação por família é lexical; a união de
tabelas exige cabeçalho repetido e não certifica completude. OCR continua
opcional, explícito e sem publicação automática. As Issues #4 e #5 permanecem
abertas.
