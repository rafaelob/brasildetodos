<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Cobertura: consulta implementada, integração pública ainda pendente

## Entrega deste incremento

Base de trabalho conferida: `33a044276220b83819e87b3d76e7a43176ea7a25`.
Plano publicado antes da implementação: `042b3cd9acf051be30a59bd557cf75d73f02f60c`.
Alterações concorrentes preservadas até `89584b82de13ab80633cb63ae96591ed94930e44`,
cuja CI Quality `34037586194` passou, incluindo build e cinco percursos de navegador.

O módulo `bdt.coverage_dashboard` implementa consultas e projeções de cobertura,
com 42 testes comportamentais em uma aplicação de teste isolada. Não está
registrado no `create_app` de produção. A escrita do arquivo central da API foi
bloqueada pela ferramenta; não foi repetida por outra rota de publicação.

A tentativa de publicar traduções/adaptação da nova interface também foi bloqueada.
Para não quebrar o main, os imports da interface e a CI foram preservados exatamente
como na revisão-base. A nova tela geral não está entregue. O painel específico de
recursos que já entrou por trabalho concorrente foi mantido e não é apresentado
como implementação exclusiva deste incremento.

## Comportamentos implementados no módulo

- Contagens de lugares elegíveis, com e sem pares completos de coordenadas,
  registros de recursos, municípios e partições por fonte/UF.
- Leitura consistente em SQLite/PostgreSQL usando a infraestrutura existente;
  não abrir um processo de coleta ao consultar o painel.
- Vocabulário público explícito para fontes e estados. Nomes arbitrários de
  datasets, caminhos, consultas de coleta, payloads, erros livres e identidades
  de usuários não fazem parte da projeção.
- Histórico paginado limitado a 50 entradas por página e 10.000 páginas; filtros
  de fonte e status com valores enumerados. Ordenação determinística por data/ID.
- Uma falha não transforma inserções tentadas em registros gravados. Contagens
  carregadas são consultadas independentemente do resultado da última tentativa.
- Processamento parcial não é conclusão nacional; presença de 27 UFs não certifica
  completude. Contadores ausentes/inválidos não se tornam números precisos.
- Datas de tentativa e referência permanecem separadas. Formatos ambíguos não são
  exibidos como datas válidas. A instalação de um pacote sem ledger de importações
  não é tratada como falha ou ausência dos dados.

## Evidência local

Suíte combinada destinada à publicação: **579 testes Python, 95,30% de cobertura
por linhas**, mantendo o piso de 85%. **42 testes Node** da interface preservada
passaram. Permanecem oito avisos de conexão SQLite não encerrada na suíte existente;
não foram filtrados. A instalação npm local falhou em resolução DNS. Build e
navegador da revisão publicada precisam de evidência da própria CI.

O catálogo público CNES anteriormente obtido foi instalado novamente em banco
novo e temporário, e as funções de consulta foram executadas sobre ele: 96.123
registros, 96.116 com coordenadas, sete sem coordenadas e 27 UFs. O histórico de
importação ausente no pacote continuou explicitamente ausente. Não houve coleta
nova nem publicação dos dados. Ver `reports/20260906-coverage-query.json`.

Este ensaio comprova a consulta do módulo sobre dados reais; não comprova registro
das rotas na aplicação, tela nova no navegador, completude cadastral ou deploy.
A medição de 0,176 segundo é uma única leitura local, não benchmark concorrente.

## Pendências prioritárias

1. Concluir integração pública do módulo e revisão da projeção do endpoint atual,
   ainda pendentes por bloqueio da ferramenta. Não declarar minimização de resposta
   no servidor como entregue; esconder um campo na interface não a substitui.
2. Publicar e validar a tela geral nos três idiomas, estados vazios/falha/repetição,
   teclado e larguras 320/390/1440. Não instalar arquivos incompletos no main.
3. Revisar o recorte de histórico legado: até 30 entradas não são o ledger completo.
   Importações de pacotes e downloads anteriores ao início de um importador devem
   ser identificados separadamente, sem inventar tentativas no banco.
4. Prosseguir com escolas nacionais, PNCP textual, demais transferências, OCR
   oficial, mapas/3D, lockfiles e operação, conforme TODO e ROADMAP.

## Atualização dos checks

Somente módulos testados e entregas já confirmadas recebem `[x]`. Itens de ligação
com a aplicação e UI permanecem abertos. Todos os commits são para main, sem
force push, branch ou PR novo. A CI do commit de código é registrada na conclusão.
