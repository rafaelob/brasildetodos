<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Estado verificado — Brasil de Todos

Atualizado em 2026-09-06. Somente `main`; sem force push ou PR de implementação novo.
Este documento separa implementação, testes, dados carregados e operação pública.

## Revisão de código e testes

Implementação integrada: `2d610889210bd1e1085a0783310f99fdf2b3869a`.
Revisão posterior dos testes: `89584b82de13ab80633cb63ae96591ed94930e44`.

Quality **34037586194**: aprovada. Backend, testes Node, build TypeScript/Vite e
cinco jornadas de navegador aprovados. A última jornada inclui Voltar/Avançar
nativos, recuperação do painel de importações e downloads de seleção.

Suíte local integrada: **537 testes Python**, **95,12% cobertura de linhas**, piso
de 85% preservado; **42 testes JavaScript**. Não é certificação universal.

Quality anterior **34037366152** e Runtime **34037366161** também aprovados para
`2d610889`; runtime verificou PostgreSQL temporário e container real read-only.
O código continua funcionando sem LLM obrigatório.

## Entregas desta continuidade

- Painel público de importações de recursos, separando registros carregados,
  tentativa mais recente e resultado concluído. Falha não apaga dados anteriores.
- Exportação de seleções de até 100 recursos em texto, CSV e JSON; filtros,
  total correspondente, quantidade exportada e truncamento explícitos.
- Preservação da exportação por recurso e revisão histórica, dos links públicos
  e das funcionalidades concorrentes já publicadas.
- Valores exatos, origens, referência temporal e integridade de versões;
  nenhuma soma entre fases ou publicação de conteúdo documental privado.
- Interface responsiva pt-BR/en/es, estados independentes de erro/recuperação
  e controles exercitados em 320, 390 e 1440 pixels.

Os testes de navegador usam UI compilada e API real com fixtures sintéticas em
banco temporário. Não são exemplos de dados oficiais publicados. Não avaliam
Safari em aparelho físico, leitor de tela, tiles/3D externos ou carga de produção.
Artefato final browser: **9990681235**.
Detalhes e hashes: `RESOURCE_STATUS_EXPORT_20260906.md`.

## Fontes oficiais — resultado separado

O catálogo CNES anteriormente verificado contém 96.123 estabelecimentos elegíveis
pelo perfil ambulatorial SUS, incluindo sete sem coordenadas, com presença em
27 UFs. Não significa completude de todos os serviços de saúde, natureza apenas
pública, vagas disponíveis ou confirmação de funcionamento atual. É um pacote
instalável verificado, não uma implantação nacional pública.

O replay de recursos **34034998849**, após a correção de precisão monetária PNCP,
recebeu 6.677 registros em 14 páginas e encontrou **invalid_resource_text**;
a importação foi revertida. Não foram publicados novos contratos PNCP por esse
ensaio. O campo/registro e sua causa exata ainda exigem diagnóstico. A alteração
textual cuja publicação foi bloqueada não integra esta entrega nem foi contornada.
Dois registros delimitados de Transferegov/Obrasgov foram aceitos em banco temporário.

A carga nacional escolar 2025 continua não concluída: tentativas anteriores de
download terminaram em ConnectTimeout. Nenhuma substituição silenciosa por
edição antiga ou dados sintéticos foi usada.

## Pendências principais

Diagnóstico e importação reconciliada PNCP; educação nacional e denominadores de
cobertura; demais módulos Transferegov, execução física/geometrias Obrasgov,
PDDE/FNS e reconciliação financeira; corpus oficial para avaliação de OCR;
mapas/3D/panoramas externos; lockfiles revisados; dispositivos e acessibilidade
assistiva; operação contínua, publicação durável, backups e rollback.

**Não há implantação pública comprovada nem declaração de conclusão integral.**
Checks e plano: `../TODO.md` e `ROADMAP.md`. A página ampla de cobertura e histórico
paginado de todas as importações segue o plano `SPRINT_20260906_COVERAGE.md`;
o painel de recursos, sozinho, não encerra aquele escopo.
