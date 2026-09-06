<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Plano de execução: cobertura compreensível e importações públicas

Atualização: 2026-09-06. Main inspecionado nesta continuação:
`c0b4f047e5c219abbbe4fe9bb89b4b486b061d23`.
O plano original foi aberto sobre `33a044276220b83819e87b3d76e7a43176ea7a25`;
o painel de recursos entrou depois, mas não encerrou a cobertura cadastral.
Trabalho somente no main, preservando inclusive a migração de runtime concorrente.
Sem force push, nova branch, dados fictícios em produção ou LLM obrigatório.

## Objetivo da rodada

Fechar uma jornada completa API → interface responsiva → teste de navegador:
explicar quais registros esta instalação carregou, quais possuem coordenadas e
como interpretar as tentativas de importação. A pessoa deve distinguir dado
carregado, fonte oficial completa, atualização do cadastro e funcionamento real.
Esta entrega não certifica ingestão nacional, integrações financeiras nem deploy.

## Sequência e TODO

- [x] U01 — Ler main, AGENTS, TODO e ROADMAP; preservar o trabalho existente.
- [x] U02 — Registrar o plano antes de implementar; revisar fontes e esquemas do código.
- [ ] U03 — API pública de resumo cadastral por tipo/UF e histórico paginado de
  importações, com filtros validados, projeção explícita e ordenação determinística.
- [ ] U04 — Contabilizar registros publicados independentemente da última
  tentativa; separar lidos, elegíveis, rejeitados e carregados conforme os dados
  realmente registrados. Não converter contagem ausente em zero nem certificar
  o país a partir da presença de 27 UFs. Reutilizar os perfis oficiais existentes.
- [ ] U05 — Frontend trilíngue com página de cobertura, indicadores legíveis,
  filtros, paginação, referências temporais, origem e estados independentes de
  carregamento, vazio, erro e recuperação. Lista deve funcionar sem mapa ou GPS.
- [ ] U06 — Testes comportamentais de API e integração: contagens, filtros,
  paginação, falha após sucesso, ausência de histórico e projeção pública sem
  caminhos, consultas internas, erros livres, credenciais ou identificadores pessoais.
- [ ] U07 — Build e jornada de navegador com API real e fixtures sintéticas
  isoladas em 320/390/1440 px e pt-BR/en/es. Validar foco, recuperação e ausência
  de overflow, mantendo todas as jornadas e pisos anteriores.
- [ ] U08 — Verificar a nova API contra o pacote CNES real já obtido, sem
  reconsultar portais ou incluir usuários; separar prova de software e cobertura.
- [ ] U09 — Publicar incrementos no main e conferir CI; atualizar os checks do
  TODO, ROADMAP e STATUS com SHA/evidências e manter explicitamente o que falta.

## Design proposto

Página acessível pela navegação principal e pelas mensagens de resultado vazio.
Topo: título simples, explicação da abrangência e referência da instalação.
Resumo: registros carregados, localizáveis no mapa e sem coordenada, sem tratar
cadastro como disponibilidade de vagas. Tabela por tipo/UF com alternativa mobile.
Histórico: tentativas paginadas por fonte e resultado; erro anterior não apaga o
catálogo. Referência do dado e data de importação são campos diferentes.
Fonte indisponível, falha de importação e filtro sem registros não são sinônimos.

## Limites e aceite

Nenhuma resposta pública deve vazar payload bruto, URL com consulta interna,
traceback, caminho local, token, usuário ou justificativa de moderação.
Os motivos públicos serão códigos controlados e mensagens traduzidas.
Contagens são do catálogo instalado, não denominadores da administração pública.
Endpoints acrescentados não podem quebrar os clientes anteriores.
Testes locais em runtime diferente são auxiliares e identificados como tal;
a validação do runtime exigido é conferida separadamente na CI.
A atualização financeira PNCP, o download educacional, OCR oficial, mapas/3D e
operação pública continuam no TODO até existirem evidências específicas.
