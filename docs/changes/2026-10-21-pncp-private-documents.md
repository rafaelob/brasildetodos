<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Documentos PNCP privados e revisitas

Lote de 21/10/2026. Base de integração no `main`: `89abc57`. O coletor está em
`7dcfce64dd2c82cb4755e8536ce6e0d9ca1650d2`; a correção do teste dependente de
meia-noite está em `968a749bb68da4857ceb49bae7ed729097749022`, SHA da suíte
integral registrada abaixo.

## O que mudou

- `backend/bdt/pncp_documents.py` lê os endpoints oficiais de documentos de
  contrato do PNCP:
  `/v1/orgaos/{cnpj}/contratos/{ano}/{sequencial}/arquivos` e o download
  documentado em `.../arquivos/{sequencialDocumento}`.
- A listagem é paginada com `pagina` e `tamanhoPagina`. O coletor aceita lista
  simples ou envelope com `data`, valida `numeroPagina`, `totalPaginas` e
  `paginasRestantes`, e interrompe sem marcar ausências quando o limite de
  páginas é atingido.
- Cada DTO é validado: CNPJ, ano, sequencial do contrato, sequencial do
  documento, título, tipo, data de publicação e URL oficial. URL fora de
  `pncp.gov.br`, com credenciais ou sem o caminho do contrato é rejeitada.
- Os bytes são baixados por operador, conferidos contra o SHA-256 retornado
  pelo download e armazenados em pasta content-addressed (`sha256/xx/<hash>`).
  A pasta é escolhida pelo operador e deve ficar fora de qualquer diretório
  estático.
- O banco guarda somente metadados oficiais allowlisted, SHA-256, tamanho,
  status, revisão e datas de coleta. Duas tabelas privadas foram adicionadas:
  `pncp_contract_documents` e `pncp_document_revisions`.
- Revisitas com os mesmos bytes e metadados não criam revisão. Mudança de bytes
  ou de metadados cria uma nova revisão e preserva o arquivo anterior.
- Documento ausente em listagem **completa** vira `not_listed`; não é apagado e
  não é chamado de cancelado. Listagem `bounded` não altera visibilidade.
- Falha de listagem ou download não altera linhas nem o último
  `collection.json` bem-sucedido. A tentativa falha fica em
  `collection-failed.json`; arquivos content-addressed já baixados antes da
  falha podem permanecer órfãos até uma limpeza operacional.
- O catálogo público exclui explicitamente as duas tabelas privadas. Não há
  rota pública, publicação automática, vínculo com lugar/recurso ou inferência
  de relação institucional a partir do título.
- CLI de operador:
  `python -m bdt.pncp_documents collect --database ... --folder ... --cnpj ... --ano ... --sequencial ...`.

## Evidência local

Python **3.14.8** (`.venv`) e Node.js **24.20.0**.

- Suíte Python integral em `968a749`: **2.166 aprovados, 17 ignorados, zero
  falhas** (6m38s). Dois avisos não bloqueantes: depreciação de
  `anyio.abc.BlockingPortal` no TestClient e Operation ID duplicado para
  `/api/health`.
- Recorte PNCP: **19 aprovados**. Catálogo/release/recuperação:
  **70 aprovados, 1 ignorado**.
- Web: **243 aprovados, zero falhas**; build TypeScript/Vite 8.2.4 aprovado.
- `npm audit --audit-level=high`: **0 vulnerabilidades** (sem mudança de
  dependências neste lote).
- A primeira execução integral encontrou uma falha de teste dependente de
  meia-noite em `test_photos.py`: a data relativa virava presente quando a
  suíte atravessava a virada local. O teste passou a usar `date.max` e a suíte
  foi executada novamente do início, já verde. Nenhum limite de produto foi
  reduzido.
- Smoke test real, um único contrato oficial: CNPJ `00394460005887`, ano
  `2024`, sequencial `7096`, documento `1`. O PNCP retornou um PDF de
  **359.547 bytes**, SHA-256
  `6c9f0232ee4e673a71dc80e2fa3d05b0f5f9bed2be3b358f6195da4284e57901`.
  A primeira coleta criou uma linha; a segunda, sem mudança, retornou
  `unchanged: 1` e não criou revisão. O arquivo temporário foi removido após a
  verificação.

## Limites

O smoke test cobre **um** contrato, não ingestão nacional de documentos. Não
houve coleta em massa, avaliação de completude do acervo PNCP, retenção/limpeza
automática de arquivos órfãos, extração de texto dos PDFs, publicação revisada,
vínculo com contratos/lugares, migração Alembic, PostgreSQL durável ou deploy.
Os documentos permanecem privados e `publication_allowed: false`. As Issues #3
e #5 permanecem abertas.
