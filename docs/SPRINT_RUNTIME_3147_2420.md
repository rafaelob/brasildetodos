<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Execução — Python 3.14.7 e Node.js 24.20.0

Solicitação do proprietário em 2026-09-06. Base inspecionada:
`5d039e0dc725e92bb1f4b12551e97e8e9d49c35f`. Trabalhar apenas no main,
preservando alterações concorrentes, sem force push e sem novos PRs.

## Plano e TODO da rodada

- [x] V01 — Conferir main, AGENTS, TODO e versões oficiais solicitadas.
- [x] V02 — Registrar o plano antes de alterar a implementação.
- [ ] V03 — Fixar Python 3.14.7 e Node.js 24.20.0 nos arquivos de versão,
  metadados dos pacotes, containers e todos os workflows; impedir deriva.
- [ ] V04 — Validar dependências e instalação nos runtimes exatos, incluindo
  PostgreSQL, extração de PDFs e testes de navegador.
- [ ] V05 — Executar backend completo, Node, build e cinco jornadas de navegador
  com a nova configuração; corrigir incompatibilidades sem baixar gates.
- [ ] V06 — Avançar uma pendência funcional comprovada, com teste comportamental,
  mantendo separação entre implementação e integração anteriormente bloqueada.
- [ ] V07 — Atualizar TODO, ROADMAP e STATUS com evidências e pendências reais.
- [ ] V08 — Publicar os commits diretamente no main e conferir SHA e CI.

## Critérios

Versões-alvo exatas não são só documentação: o ambiente deve reportá-las.
Node 24.20 é interpretado como 24.20.0. Não usar fallback silencioso para
Python 3.13 ou Node 22 quando o runtime solicitado não estiver disponível.
O ambiente local pode oferecer outra versão; seus testes são auxiliares,
não prova de execução no runtime solicitado. Não alterar dados de produção,
publicar observações privadas nem alegar ingestão/deploy por testes sintéticos.

## Pendências maiores preservadas

Ingestão nacional educacional, erro textual PNCP, integrações financeiras amplas,
OCR em corpus oficial, mapas/3D/panoramas, acessibilidade assistiva, lockfiles,
atualização e publicação durável dos dados, moderação e implantação pública.
Consultar também TODO.md e docs/ROADMAP.md. Esta migração não encerra esses itens.

## Fontes oficiais consultadas

- https://www.python.org/downloads/release/python-3147/
- https://nodejs.org/en/download/archive/v24.20.0
