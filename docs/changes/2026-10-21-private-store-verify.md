<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Verificação de integridade do armazenamento privado

Lote de 21/10/2026. Base de integração no `main`: `cdcae95`. Código e testes
deste lote em `3a4f68e8a9a65f8de287771ad9d2c2bc172e2b11`.

## O que mudou

- `bdt.private_store_admin verify` percorre cada hash e tamanho referenciado por
  `pncp_contract_documents`, `pncp_document_revisions` e `document_originals`.
- Para cada referência, confere presença do arquivo regular, tamanho e SHA-256
  com `private_store.verified_path`. O relatório separa `ok`, `missing`,
  `corrupt` e erros, sem alterar arquivos.
- O comando é de operador, não tem rota pública e usa a mesma pasta privada
  content-addressed dos originais e documentos PNCP.
- A CLI agora aceita `verify` e `prune`; ambos usam `--database` e `--folder`, e
  `prune` continua dry-run por padrão.

## Evidência local

Python **3.14.8** (`.venv`).

- Suíte Python integral em `3a4f68e`: **2.178 aprovados, 17 ignorados, zero
  falhas** (6m35s). Dois avisos não bloqueantes: depreciação de
  `anyio.abc.BlockingPortal` no TestClient e Operation ID duplicado para
  `/api/health`.
- Recorte de armazenamento privado: **4 aprovados** (verificação saudável,
  arquivo ausente, bytes alterados e CLI dry-run).
- O teste cobre referência atual do PNCP, revisão antiga do PNCP e original
  documental. Web não foi alterada; a última execução permanece **243
  aprovados** e build Vite 8.2.4 aprovado.

## Limites

A verificação usa apenas as tabelas do banco informado; não prova que um backup
externo existe, não restaura bytes e não corrige arquivos. Ela não substitui
backup, política de retenção/expurgo, PostgreSQL durável, Alembic ou deploy. Se
um arquivo estiver ausente ou corrompido, o operador precisa recuperá-lo da
fonte/backup antes de usá-lo como evidência. As Issues #4 e #5 permanecem
abertas.
