<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Plano vivo de implementação — Brasil de Todos

Atualização: 06/09/2026. Trabalho exclusivamente no `main`, sem force push.
`[x]` significa entrega implementada e evidência identificada, não conclusão
integral do produto. Código publicado, teste aprovado, carga oficial e deploy
são resultados distintos. Execução por tarefa: `../TODO.md`.

## P0 — Catálogo nacional e publicação operacional

- [x] Importação territorial IBGE e reuso de snapshot com proveniência preservada.
- [x] CNES: perfil do arquivo oficial, quarentena, relatório por UF e pacote público verificável. 96.123 elegíveis, 27 UFs, sete sem coordenadas; execução `34007758949`, aceite API `34008771230`.
- [x] Inep: descoberta da edição, leitura apenas de tabelas escolares, validação de encoding/identidade/ano/município/UF, transação e relatório; 44 testes da implementação inicial.
- [ ] Concluir download e carga real da edição 2025. Tentativas terminaram em ConnectTimeout; não substituir por amostra ou edição antiga sem declarar.
- [ ] Reconciliar e certificar partições escolares e de saúde com denominadores publicados. Presença em 27 UFs não é certificado de completude ou funcionamento.
- [x] Instalação atômica de pacote público sem contas, sessões ou observações pessoais.
- [x] Agregação cartográfica independente da página da lista; contabilidade de 96.116 pontos CNES verificada na API.
- [ ] Completar cobertura cadastral detalhada e histórico paginado de importações conforme `SPRINT_20260906_COVERAGE.md`; o painel de recursos abaixo não encerra essa jornada mais ampla.
- [ ] Publicação durável do catálogo, atualização periódica, indicadores de atraso e alertas operacionais.
- [ ] Hospedagem, domínio/HTTPS, backups/restauração e rollback exercitados numa implantação pública.

## P0 — Recursos, contratos e intervenções

- [x] Editor documental privado e vínculos por trecho literal, revisão independente, publicação e retratação sem alocação automática de dinheiro.
- [x] Inspeção de esquemas PNCP, Transferegov Especiais e Obrasgov no runner (`34009291326`). Não depender de API futura.
- [x] Perfis de metadados de contratos PNCP, planos de ação especiais e projetos Obrasgov, com valores, direção de orçamento e escopo territorial separados.
- [x] Coleta paginada verificável, retomada, transação por consulta completa, versões imutáveis e detecção de regressão/conflito.
- [x] Representação de até quatro casas decimais nos metadados monetários PNCP sem arredondamento silencioso; eventos de pagamento continuam no contrato próprio em centavos (`e4d2554d`).
- [x] HTTP 204 inicial vazio em endpoints PNCP explicitamente admitidos; vazio inesperado após páginas com registros continua falha. Não apagar dados anteriores.
- [x] Busca trilíngue de recursos por título/objeto, fonte e UF, valores separados e versões.
- [x] Links públicos de consulta/recurso, preservação de filtros e teste nativo de Voltar/Avançar sem parâmetros privados.
- [x] Exportação pública por recurso/revisão e por seleção de até 100 registros em texto, CSV e JSON; filtros, contagens, truncamento, precisão e fontes explícitos. Sem total combinado entre fases.
- [x] Painel público de importações de recursos com projeção mínima, última tentativa/sucesso e dados anteriores preservados após falha; erro/recuperação independentes da busca.
- [x] Um plano Especiais e um projeto Obrasgov reais importados e consultados por identidade em banco temporário (`34010343797`). Isso não é carga nacional financeira.
- [ ] Concluir importação PNCP da consulta real. O replay `34034998849` recebeu 6.677 registros/14 páginas e, após a correção monetária, encontrou `invalid_resource_text`; rollback integral. Identificar legitimamente campo/registro e causa antes de alterar o perfil. Alteração bloqueada não foi contornada.
- [ ] Ampliar todos os módulos/tabelas Transferegov: assinatura, instrumentos, metas, etapas, aditivos, desembolsos e pagamentos; plano especial não é convênio.
- [ ] Fila de anexos referenciados, metadados, hashes, retenção e revisão.
- [ ] Geometrias e execução física Obrasgov sem tratar endereço do comprador como local da obra.
- [ ] PDDE/FNS preservando granularidade e identificadores das unidades.
- [ ] Reconciliação entre sistemas, estornos/correções e destinatários, sem dupla contagem.
- [ ] Scheduler temporal com janelas sobrepostas, revisitas, monitoramento de esquema e operação durável. Coleta paginada e suporte a 204 não encerram esse scheduler.

## P0/P1 — Documentos e OCR

- [x] Texto nativo, posições, tabelas e candidatos privados, sem publicação automática.
- [x] OCR seletivo local com original preservado, autorização, lease, rollback e recuperação de tarefa interrompida.
- [x] Uma página digitalizada sintética em português processada por Tesseract real (`34008123457`). Evidência de integração, não acurácia em corpus oficial.
- [ ] Corpus oficial legitimamente obtido e anotado, métricas por campo, abstenção, documentos multipágina/assinados e tabelas fragmentadas.
- [ ] Quotas, cancelamento, retenção, expurgo e observabilidade da fila operacional.
- [ ] Extração por família documental, aditivos e prazos avaliada com documentos reais.
- [ ] Política de reexibição de documentos, dados pessoais e derivados verificada antes de abertura ampla.

## P0 — Frontend, design e qualidade

- [x] Interface de recursos, importações e ações de compartilhar/exportar responsiva nos três idiomas, com estados independentes e foco/controles exercitados no navegador.
- [x] Cinco jornadas compiladas contra API real com fixtures sintéticas isoladas: consulta/favoritos/colaboração; revisão documental/privacidade; recursos/histórico; compartilhamento/versões; importações/seleções/Voltar/Avançar.
- [x] CI Quality `34037586194` aprovada para `89584b82de13ab80633cb63ae96591ed94930e44`: backend, testes Node, build TypeScript/Vite e navegador. Larguras exercitadas 320/390/1440.
- [x] Suíte local integrada: 537 Python, 95,12% linhas, piso 85% mantido; 42 JavaScript. Medição delimitada, não prova universal.
- [ ] Acessibilidade assistiva, avaliação WCAG integral, Safari/dispositivos físicos, WebGL limitado e testes de carga.
- [ ] Lockfiles transitivos revisados, build reproduzível, auditoria de dependências e exceções justificadas.
- [ ] Benchmarks de consultas nacionais, índices e uso de memória, com base real e concorrência representativa.

## P0 — Colaboração, privacidade e operação

- [x] Autenticação, CSRF, revisão independente, exportação/desativação de conta, retirada de observação e retratação documental.
- [x] Ensaios PostgreSQL e container não-root/read-only no runner; backup SQLite consistente com WAL e restauração em destino novo. Runtime `34037366161` aprovado; não equivale a operação cloud.
- [ ] Recuperação de conta, recurso do autor, retenção, equipe e processo de moderação.
- [ ] Operação com banco durável, credenciais de menor privilégio, alertas e recuperação testada no ambiente público.

## P1/P2 — Experiência territorial e expansão

- [ ] Panoramax/Mapillary opcionais com captura, origem e licença; imagem histórica não é visita atual.
- [ ] Tiles e 3D reais testados sem bloquear lista, pesquisa e participação.
- [ ] Grupos, tarefas e histórico coletivo, sem incentivar acusações ou exposição de pessoas.
- [ ] Fotos com remoção de metadados, revisão, exclusão e política operacional.
- [ ] IBGE por setores, métodos de acesso, conectividade escolar/Giga e camadas globais conforme utilidade e licença.
- [ ] Auditoria de licença por fonte, governança e documentação de contribuição.

## Ordem de execução seguinte

1. Resolver pendências de dados reais: diagnóstico PNCP e carga nacional educacional; manter resultados de software separados.
2. Completar cobertura cadastral e publicação/atualização durável com manifestos.
3. Expandir instrumentos, documentos e reconciliação financeira sem vínculos inventados.
4. Validar mapa/3D, acessibilidade, desempenho e operação; realizar deploy público real.

Registro desta entrega: `RESOURCE_STATUS_EXPORT_20260906.md`.
Histórico de entregas: `MAIN_IMPLEMENTATION_20260906.md`, `RESOURCE_IMPLEMENTATION_20260906.md`, `RESOURCE_PRECISION.md` e `RESOURCE_SHARING.md`.
Não apresentar percentual global de pronto. O projeto permanece sem implantação pública comprovada e sem declaração de conclusão integral.
