<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Lote de entrega: jornadas completas e evidências

Base inspecionada: b12716600bae2d5c0855e54116a5a62914408852.
Python 3.14.7, Node 24.20.0; somente main, sem force push.
Os pacotes locais anteriores serão comparados ao código atual, nunca copiados
sobre alterações concorrentes. A aplicação usa dados carregados; testes isolados
não são seed de produção e não substituem coletas oficiais.

## Plano e checklist

- [x] D01 — Ler main, AGENTS e TODO; obter e verificar o snapshot exato.
- [x] D02 — Registrar plano antes de alterar código.
- [ ] D03 — Auditar as jornadas integradas, estado dos conectores, testes e
  artefatos; identificar entregas ainda não expostas ou somente parciais.
- [ ] D04 — Fechar o próximo fluxo vertical de produto com persistência real,
  validação no backend e interface pt-BR/en/es, sem respostas simuladas.
- [ ] D05 — Acrescentar testes de comportamento, limites, rollback, estados
  vazios/erro/recuperação e descarte de respostas atrasadas.
- [ ] D06 — Executar a aplicação compilada no navegador em 320/390/1440 px;
  inspecionar o design e preservar todos os testes anteriores.
- [ ] D07 — Reexecutar as coletas oficiais pertinentes e conferir artefatos
  por bytes/hash/contagens; registrar falha de fonte separada de teste de código.
- [ ] D08 — Atualizar TODO/ROADMAP/STATUS com conclusão verificável e inventário
  de pendências por frontend, dados, backend, colaboração, OCR e operação.
- [ ] D09 — Publicar commits diretamente em main e conferir CI nos runtimes
  exatos; instalação de produção e validação dos dados são resultados separados.

## Critérios de aceite

Sem mocks/stubs em fluxos de produção. Fixtures e transportes simulados apenas
em testes determinísticos identificados. Não enfraquecer autenticação, revisão,
limites, proveniência ou qualidade para encerrar checks. Requisitos de dados
nacionais e operação pública não são marcados concluídos sem execução real.
