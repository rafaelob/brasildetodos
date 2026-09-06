<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Meus lugares — consulta e componentes; integração pública pendente

A publicação da alteração em `backend/bdt/api.py` foi bloqueada pela ferramenta
nesta execução. Ela não foi repetida por outro meio. A API de produção e a
navegação principal permanecem inalteradas. Este incremento publica o módulo
consultável, os componentes e testes isolados, não a jornada pública concluída.

## Entrega independente

`watch_summary(database, WatchRequest(...))` lê de 1 a 30 identificadores e até
cinco versões por lugar, em duas consultas sob snapshot consistente. Preserva
fontes de ambas as versões, não registra favoritos no servidor, não associa
primeiro registro à inauguração e distingue mudança de referência de conteúdo.
Campos não previstos são excluídos. Incoerência de coluna/fingerprint/histórico
produz `unavailable` só para o item afetado. Ausência não significa fechamento.

O adaptador `install` é registrado explicitamente apenas no app de teste. Os
componentes `SavedPlaces.tsx`, os helpers e estilos estão prontos para integração
futura; não substituem a tela atual. A compilação verifica tipos dos componentes,
mas não equivale a navegar uma funcionalidade não conectada.

## Validação

35 testes comportamentais da consulta/adaptador isolado; 14 testes JavaScript.
Um teste usa duas conexões SQLite e uma atualização concorrente real para provar
que a leitura não combina a ficha antiga e o histórico novo. O aceite de catálogo
reinstala o pacote e testa a consulta interna; seu relatório identifica
`query_module_only_not_public_endpoint`. Nenhum dado sintético é publicado.

## Para concluir a jornada

Registrar o adaptador na API de produção, integrar `SavedPlaces` na navegação,
executar uma jornada nativa contra o build atual e validar estados por teclado,
idioma e tamanho de tela. Esses itens permanecem abertos no TODO. As fontes reais
conferidas e o resultado dos testes serão registrados separadamente.
