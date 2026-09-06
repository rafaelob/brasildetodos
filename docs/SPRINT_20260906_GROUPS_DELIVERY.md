<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Lote — grupos, tarefas e validação real

Base inspecionada: a333e0eec4e072547d08dbe95f73ae284dd6dfb9.
Python 3.14.7 e Node 24.20.0; trabalho somente no main, sem force push.
Preservar o código já integrado de favoritos, cobertura, comparação, visitas,
região e instalação de recursos. Pacotes locais anteriores não substituem main.

## Plano executável

- [x] G01 — Conferir main, AGENTS, TODO, código e CI existentes; obter snapshot exato.
- [x] G02 — Registrar plano antes de alterar o produto.
- [ ] G03 — Persistir grupos privados, membros, convites revogáveis/expiráveis e
  tarefas associadas a lugares reais do catálogo, com quotas e controle de versão.
- [ ] G04 — Implementar assumir tarefa, entregar observação própria, revisão
  independente e reabertura; conclusão de tarefa nunca publica a observação.
- [ ] G05 — Integrar exportação/desativação de conta, saída e revogação de acesso;
  sem exposição de grupos, tokens, rascunhos ou identidades nos endpoints públicos.
- [ ] G06 — Integrar interface PT-BR/EN/ES, navegação, formulários, estados,
  paginação, teclado, conflito de versão e recuperação de falhas.
- [ ] G07 — Testes comportamentais de autenticação, CSRF, isolamento, concorrência,
  tokens, limites, persistência, exclusão e revisão; nenhum mock na produção.
- [ ] G08 — Build e jornada nativa multiusuário nos runtimes exatos, mantendo as
  jornadas anteriores e verificando 320/390/1440 pixels.
- [ ] G09 — Retomar a coleta escolar oficial com parâmetros existentes e registrar
  seu resultado; validar artefatos reais separadamente dos fixtures de teste.
- [ ] G10 — Reconciliar TODO/ROADMAP/STATUS, criar matriz de features e bloqueios.
- [ ] G11 — Publicar commits atômicos no main, conferir referência e CI final.

## Critérios

Consultar sem conta permanece possível; contribuir exige autenticação e CSRF.
Convite não promove ninguém a revisor da plataforma. Grupo é privado e não é
canal oficial. Revisor de tarefa deve ser diferente do autor da entrega. Uma
observação retirada/desativada deixa de sustentar conclusão visível. Tokens só
aparecem ao criar convite e nunca entram nos logs, hashes de URL ou exportações.
Não inserir dados sintéticos em produção, nem inferir geometrias/vínculos/pagamentos.
Fixtures isolados continuam necessários para testar falhas sem afetar cidadãos.

## Escopo restante que precisa continuar visível

Educação 2025 e denominadores; competências CNES; demais módulos Transferegov,
Obrasgov, PDDE/FNS e reconciliação; corpus oficial OCR; filas/retencão e fotos;
mapas/3D/panoramas externos; acessibilidade assistiva e dispositivos; domínio,
HTTPS, atualização durável, monitoramento, backup/restauração e deploy autorizado.
Um lote aprovado não será confundido com conclusão de todas essas frentes.
