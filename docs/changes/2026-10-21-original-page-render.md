<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Prévia da página original no revisor

Lote de 21/10/2026. Base de integração no `main`: `ced0039`. Código e testes
deste lote em `d458b4a323b0baedebeea82376ce880c52447782`.

## O que mudou

- `backend/bdt/document_render.py` renderiza **uma** página do PDF original para
  PNG usando `pdftoppm` local, sem rede, OCR ou publicação. Limita página
  (1..1000), DPI (72..300), tempo (1..300 s) e saída (16 MiB), e exige cabeçalho
  PNG.
- `GET /api/workbench/documents/{id}/pages/{page}/image` exige revisor,
  revalida o original armazenado e responde `image/png` com `no-store` e
  `nosniff`. Sem Poppler, a rota responde 503; timeout responde 504.
- O Workbench mostra a imagem acima do texto extraído quando o original está
  armazenado. Se o renderizador não existir ou falhar, a imagem é ocultada e o
  texto/listas continuam utilizáveis.
- O filtro de caminhos do `Quality` passou a observar `document_render.py`.

## Evidência local

Python **3.14.8** (`.venv`) e Node.js **24.20.0**.

- Suíte Python integral em `d458b4a`: **2.183 aprovados, 17 ignorados, zero
  falhas** (9m02s). Dois avisos não bloqueantes: depreciação de
  `anyio.abc.BlockingPortal` no TestClient e Operation ID duplicado para
  `/api/health`.
- Recorte de renderização, originais, features e API: **66 aprovados**.
- Web: **243 aprovados, zero falhas**; build TypeScript/Vite 8.2.4 aprovado.
- A renderização real com Poppler **não foi executada** neste ambiente; os
  testes substituem o processo por um PNG sintético e verificam os limites, a
  autorização e os erros. A presença de `pdftoppm` não é requisito do núcleo.

## Limites

Sem Poppler instalado, a prévia visual não aparece, mas a extração e a lista
continuam funcionando. Não há zoom/pan próprio, anotação sobre a página,
renderização de múltiplas páginas, corpus oficial, upload HTTP, deploy,
PostgreSQL durável ou Alembic. A imagem é privada e exige revisor. A Issue #4
permanece aberta.
