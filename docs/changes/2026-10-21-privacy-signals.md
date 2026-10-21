<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Sinais de privacidade e assinatura na extração documental

Lote de 21/10/2026. Base de integração no `main`: `688bf36`. Código e testes
deste lote em `b6dba7f49f8f7163349a9d6b505c321e955bbc04`.

## O que mudou

- `bdt.documents` passa a registrar `privacy_flags` por página para CPF
  formatado, CPF com contexto, e-mail, telefone com contexto ou DDD, RG com
  contexto e termos de assinatura (`assinatura`, `assinado por`,
  `assinado digitalmente`, `signatário`).
- Cada flag guarda somente `kind`, `start` e `end`; o valor encontrado não é
  copiado para o resumo de privacidade. O texto privado continua apenas na
  extração restrita e no original.
- O documento recebe um resumo `privacy` com `review_required`, tipos e páginas,
  rotas não nativas e `publication_allowed: false`. Páginas
  `ocr_candidate`, `review_encoding`, `hybrid_review`, `review_orientation` ou
  em branco exigem revisão de privacidade mesmo sem sinal lexical.
- O Workbench mostra um aviso com os tipos sinalizados após carregar a página.
  Os rótulos foram adicionados em pt-BR, en e es; nenhum valor pessoal é enviado
  ao aviso.
- O corpus OCR sintético foi rederivado pelo mesmo extrator `native-pdf-v2`.
  Os PDFs originais, o texto reconhecido e a ausência de OCR permanecem
  inalterados; o manifesto registra o novo hash de `native-extraction.json`.
- `docs/DOCUMENT_OCR.md` e a matriz de capacidades foram atualizados para deixar
  claro que sinal lexical não é anonimização nem conclusão jurídica.

## Evidência local

Python **3.14.8** (`.venv`) e Node.js **24.20.0**.

- Suíte Python integral em `b6dba7f`: **2.174 aprovados, 17 ignorados, zero
  falhas** (6m35s). Dois avisos não bloqueantes: depreciação de
  `anyio.abc.BlockingPortal` no TestClient e Operation ID duplicado para
  `/api/health`.
- Recorte documental/OCR/corpus: **94 aprovados**; estrutura documental: **7
  aprovados**. Recorte de API, features, originais e PNCP: **80 aprovados**.
- Web: **243 aprovados, zero falhas**; build TypeScript/Vite 8.2.4 aprovado.
- `python -m compileall -q backend` e
  `git -c core.whitespace=cr-at-eol diff --check`: aprovados.
- O teste sintético confirma CPF, e-mail, telefone e assinatura, e confirma que
  o resumo de privacidade não contém os valores brutos.

## Limites

A detecção é lexical e conservadora; não é anonimização, não prova ausência de
dado pessoal e não detecta assinatura imagética sem texto. O texto de OCR não é
varrido retroativamente por novos padrões. Não houve política de expurgo,
retenção, revisão humana em corpus oficial, publicação, migração Alembic,
PostgreSQL durável ou deploy. A Issue #4 permanece aberta.
