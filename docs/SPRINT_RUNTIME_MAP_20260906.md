<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Continuidade: runtimes exatos e mapa utilizável

Base inspecionada: `d649880cfd010420e09f6371a609105286c6477c`.
Python **3.14.7** e Node.js **24.20.0**, conforme solicitação do proprietário.
Somente main; preservar atualizações concorrentes e nunca forçar a referência.

## Trabalho existente preservado

A base já fixa runtimes, incorpora lockfiles e verifica instalação sem resolver
fallback. Quality `34040969868` e runtime `34040969898` passaram. Conferir a nova
revisão separadamente. O ambiente local Python 3.13/Node 22 só serve a verificações
auxiliares; não é prova de execução nas versões solicitadas.

## TODO desta continuidade

- [x] M01 — Consultar main, AGENTS, TODO, migração existente e fontes oficiais.
- [x] M02 — Registrar o plano antes de alterar os componentes.
- [ ] M03 — Corrigir empacotamento do worker MapLibre v6 no Vite, preservando carregamento sob demanda.
- [ ] M04 — Impedir pontos de filtros antigos após falha; tratar carga, repetição, desligamento e descarte do mapa.
- [ ] M05 — Selecionar a camada de edificações efetivamente declarada no estilo; distinguir 3D disponível de altura ausente e respeitar movimento reduzido.
- [ ] M06 — Testes de políticas do mapa e navegador real com WebGL, worker, pontos e polígonos sintéticos explicitamente isolados; conferir lista sem mapa.
- [ ] M07 — Execução separada e limitada com estilo/tiles externos, sem fingir disponibilidade nacional de 3D ou panoramas.
- [ ] M08 — Reexecutar backend, Node, build, navegador e runtime nas versões fixadas; conferir locks e atualizar checks sustentados por resultados.
- [ ] M09 — Consolidar TODO, ROADMAP e STATUS, publicar no main e confirmar referências.

## Limites e pendências preservados

Não contornar operações anteriormente bloqueadas. A integração pública da nova
consulta geral de cobertura e o ajuste textual PNCP continuam separados deste
incremento. Não gerar dados de produção sintéticos. Nenhuma relação instituição /
contrato será deduzida de proximidade. Nenhuma imagem de mapa comprova atendimento.

Continuam pendentes a carga nacional de escolas, reconciliação financeira ampla,
OCR em corpus oficial, grupos/fotos, acessibilidade assistiva/dispositivos físicos,
publicação durável e implantação pública. Uma suíte verde não encerra esses itens.

## Referências de implementação

- https://www.python.org/downloads/release/python-3147/
- https://nodejs.org/en/download/archive/v24.20.0
- https://maplibre.org/maplibre-gl-js/docs/ — worker Vite `?worker&url` para v6.
- https://maplibre.org/maplibre-gl-js/docs/examples/display-buildings-in-3d/
