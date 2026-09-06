<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# TODO de implementação — Brasil de Todos

Atualizado em 2026-09-06. Base inspecionada: `e4d2554dfb59386d8e4fd3851c65d9d15974bd79`.
Trabalho somente no `main`, sem force push. Este checklist acompanha a execução;
`docs/ROADMAP.md` mantém a visão completa. Só marcar `[x]` com código e evidência.
Código implementado, teste aprovado, coleta real e deploy são resultados distintos.

## Rodada em execução — concluir integração e compartilhamento

- [x] R01 — Ler main e AGENTS; comparar o incremento anterior com alterações remotas antes de integrar.
- [x] R02 — Registrar plano de backend, frontend, design e testes antes de alterar o produto.
- [ ] R03 — Integrar painel público de importações e tratamento de estados sem expor consultas, arquivos ou dados privados.
- [ ] R04 — Criar exportação pública limitada de recursos/histórico, com precisão preservada, filtros, referências e indicação de truncamento.
- [ ] R05 — Criar consultas compartilháveis e navegação voltar/avançar, sem incluir favoritos, credenciais ou contribuições privadas na URL.
- [ ] R06 — Aprimorar leitura mobile, ações de compartilhar/exportar, estados de carregamento/erro e acessibilidade nos três idiomas.
- [ ] R07 — Testar API, precisão, limites, privacidade, histórico, filtros e tradução; manter gates anteriores.
- [ ] R08 — Publicar no main e executar build e percursos reais de navegador, corrigindo falhas sem remover testes.
- [ ] R09 — Consultar o replay real PNCP após correção; registrar contagem, causa comprovada ou bloqueio sem inferir sucesso.
- [ ] R10 — Atualizar os checks abaixo e ROADMAP/STATUS, registrando SHA testado e pendências nacionais/deploy.

## Rodada anterior — dados, API, experiência e qualidade

- [x] T01 — Consultar main, contrato AGENTS e pendências reais do roadmap.
- [x] T02 — Registrar este plano antes da implementação.
- [ ] T03 — Reproduzir a falha monetária e definir tratamento sem arredondamento silencioso; diagnóstico limitado aos campos necessários.
- [x] T04 — Implementar representação/validação monetária que preserve a precisão publicada e sua limitação, com testes de regressão.
- [x] T05 — Tratar respostas PNCP vazias HTTP 204 e recuperação/paginação sem fabricar completude ou apagar registros.
- [ ] T06 — Melhorar frontend de Obras e recursos: hierarquia visual, leitura dos valores, estados e histórico; preservar lista acessível e idiomas.
- [ ] T07 — Implementar consulta compartilhável e resumo/exportação pública dos recursos, sem dados de usuários ou conteúdo documental privado.
- [ ] T08 — Testar API, integração, rollback, imutabilidade, formatação e fluxos pt-BR/en/es; manter o piso de cobertura existente.
- [ ] T09 — Executar build e os percursos reais de navegador em 320/390/1440 pixels; corrigir defeitos sem remover gates.
- [ ] T10 — Reexecutar uma consulta oficial delimitada; registrar resultado real separadamente da suíte sintética.
- [ ] T11 — Atualizar ROADMAP, STATUS e registro de implementação com resultados, limitações e próximos passos.
- [ ] T12 — Confirmar commits no main e resultados de CI da revisão publicada.

### Evidência parcial da rodada anterior

T04/T05: 478 testes Python (95,05% linhas, piso 85% mantido), 30 Node.
Manual PNCP Consulta v1, p. 37: valores cadastrais admitem quatro casas;
p. 38: 204 representa ausência de conteúdo. O parser agora preserva frações
como texto decimal, sem alterar o contrato de eventos em centavos. HTTP 204
só encerra a primeira página vazia dos endpoints PNCP explicitamente aceitos;
resposta vazia posterior, total conflitante ou outro provedor continuam falhas.
A suíte é determinística; a reexecução oficial e o build remoto têm evidências
próprias. T03 permanece aberto até confirmar o resultado da janela real.

## Pendências nacionais e de lançamento (não dadas como concluídas)

- [ ] N01 — Obter e importar a edição nacional 2025 do Censo Escolar e reconciliar partições.
- [ ] N02 — Certificar a cobertura dos catálogos com denominadores e relatórios, não apenas presença nas UFs.
- [ ] N03 — Ampliar instrumentos/metas/etapas/aditivos/pagamentos Transferegov e execução física/geometrias Obrasgov.
- [ ] N04 — Reconciliar registros financeiros entre fontes, estornos e destinatários; integrar PDDE/FNS preservando granularidade.
- [ ] N05 — Avaliar extração/OCR em corpus oficial obtido legitimamente, com métricas por campo e revisão humana.
- [ ] N06 — Testar mapas/3D externos e panoramas opcionais, sem bloquear o núcleo.
- [ ] N07 — Incorporar lockfiles revisados, validar acessibilidade assistiva e dispositivos físicos.
- [ ] N08 — Definir e validar hospedagem, HTTPS, publicação durável dos dados, atualização periódica, backups e rollback.
- [ ] N09 — Expandir grupos/tarefas, fotos e moderação somente com privacidade, retenção e responsabilidade operacional.

## Critérios de aceite

Sem dados sintéticos em produção, sem vínculo de unidade por nome/proximidade,
sem soma de fases financeiras, sem LLM obrigatório e sem afirmação de deploy
baseada em teste local. Três idiomas e informação de origem/data em toda ficha.
Manter explícitas indisponibilidade da fonte, ausência de dado e falha de coleta.
