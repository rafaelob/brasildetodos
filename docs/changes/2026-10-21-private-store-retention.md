<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Limpeza de órfãos no armazenamento privado

Lote de 21/10/2026. Base de integração no `main`: `25cdc49`. Código e testes
deste lote em `b065f42a7a5191d4998e09d5a1d37534042faa53`.

## O que mudou

- `backend/bdt/private_store_admin.py` adiciona `prune` para o store
  content-addressed compartilhado por documentos PNCP e originais de evidência.
- A referência é calculada pelas tabelas atuais e pelo histórico:
  `pncp_contract_documents`, `pncp_document_revisions` e
  `document_originals`. Um hash presente em qualquer revisão antiga é
  preservado.
- O padrão é **dry-run**. `--apply` só remove arquivos com nome SHA-256 válido,
  sem referência e mais antigos que `--older-than-days` (padrão 30). Arquivos
  recentes, nomes desconhecidos e symlinks são mantidos.
- Arquivos de diretórios de prefixo não reconhecidos não são varridos. Erros de
  remoção são devolvidos no relatório, sem apagar o restante por causa de um
  arquivo.
- A CLI é de operador e não tem rota pública:
  `python -m bdt.private_store_admin prune --database ... --folder ... [--older-than-days N] [--apply]`.

## Evidência local

Python **3.14.8** (`.venv`).

- Suíte Python integral em `b065f42`: **2.177 aprovados, 17 ignorados, zero
  falhas** (6m52s). Dois avisos não bloqueantes: depreciação de
  `anyio.abc.BlockingPortal` no TestClient e Operation ID duplicado para
  `/api/health`.
- Recorte de retenção: **3 aprovados**. Recorte de retenção, originais e PNCP:
  **29 aprovados**.
- O teste cobre dry-run sem remoção, aplicação removendo somente o órfão antigo,
  preservação do hash atual e da revisão anterior do PNCP, preservação do
  original documental, arquivo recente e nome inválido.
- Web: **243 aprovados, zero falhas**; build TypeScript/Vite 8.2.4 aprovado.

## Limites

A ferramenta limpa somente arquivos sem referência no banco consultado; não
substitui backup, não define retenção legal dos documentos referenciados, não
remove originais publicados e não executa expurgo automático. Um operador ainda
precisa decidir e executar `--apply` com a pasta e o banco corretos. Não houve
PostgreSQL durável, Alembic, deploy ou validação de restauração. As Issues #4 e
#5 permanecem abertas.
