<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Originais documentais privados e download de revisor

Lote de 21/10/2026. Base de integração no `main`: `79e2a07`. Código e testes
deste lote em `ea21f1db87bf4dd147d9da9de742347315b8846d`.

## O que mudou

- `backend/bdt/private_store.py` concentra o armazenamento content-addressed já
  usado pelos documentos PNCP: caminho por SHA-256, verificação de arquivo
  existente, recusa de symlink e conferência do hash depois da cópia/movimento.
- `backend/bdt/document_originals.py` adiciona a tabela privada
  `document_originals` e o comando de operador:
  `python -m bdt.document_originals store --database ... --folder ... --document-id ... --path ... --operator ...`.
- O original só é aceito se for um PDF de até 32 MB e se o SHA-256 for idêntico
  ao `snapshot_sha256` já registrado na fonte do documento. O operador precisa
  ser um revisor existente; a operação é auditada.
- O armazenamento é idempotente para os mesmos bytes. O arquivo de origem
  permanece no lugar; o store recebe uma cópia. Um hash divergente, um arquivo
  que não é PDF ou um operador inexistente são recusados antes da gravação.
- `GET /api/workbench/documents/{id}/original` exige revisor autenticado,
  confere novamente tamanho e SHA-256 antes de responder e envia o PDF como
  anexo com `no-store` e `nosniff`. Não existe rota pública para o original.
- A listagem de documentos e a resposta de página informam
  `has_original`/`original_available`. O Workbench mostra o link de download
  somente quando o original está armazenado; o texto extraído continua sendo a
  superfície de revisão.
- `.env.example` e `docs/configuration.md` passam a declarar
  `BDT_DOCUMENT_STORE`, com padrão em `BDT_DATA_DIR/document-originals`, fora
  do diretório estático. `docs/OPERATIONS.md` documenta o comando e a pasta
  privada. O filtro de caminhos do workflow `Quality` inclui os novos módulos de
  armazenamento privado.

## Evidência local

Python **3.14.8** (`.venv`) e Node.js **24.20.0**.

- Suíte Python integral em `ea21f1d`: **2.173 aprovados, 17 ignorados, zero
  falhas** (6m58s). Dois avisos não bloqueantes: depreciação de
  `anyio.abc.BlockingPortal` no TestClient e Operation ID duplicado para
  `/api/health`.
- Recorte de originais: **7 aprovados**; recorte de documentos PNCP e originais:
  **26 aprovados**. Catálogo/release/schema: **61 aprovados, 1 ignorado**.
- Web: **243 aprovados, zero falhas**; build TypeScript/Vite 8.2.4 aprovado.
- `python -m compileall -q backend` e
  `git -c core.whitespace=cr-at-eol diff --check`: aprovados.
- Nenhum PDF oficial ou de pessoa real foi commitado; os testes usam bytes
  sintéticos com cabeçalho `%PDF-`.

## Limites

O armazenamento é feito por CLI de operador; não há upload HTTP de original,
editor visual/zoom sobre a página original, extração nova a partir do original,
publicação automática, retenção/limpeza de arquivos órfãos, backup do store,
migração Alembic, PostgreSQL durável ou deploy. SHA-256 prova integridade, não
substitui backup. O download exige revisor e não cria vínculo com lugar ou
recurso. As Issues #4 e #5 permanecem abertas.
