<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# TODO de implementação — Brasil de Todos

Atualizado em 2026-09-06. Código verificado: `89584b82de13ab80633cb63ae96591ed94930e44`.
Trabalho somente no `main`, sem force push. `docs/ROADMAP.md` mantém a visão completa.
Só marcar `[x]` com implementação e evidência. Código, testes, coleta oficial e
implantação pública são resultados distintos. Os checks abaixo não certificam
cobertura nacional nem conclusão integral do projeto.

## Continuidade — backend, frontend, design, publicação e testes

Plano R registrado em `68a979062603bcd8d0604b9738cf961e2c1d3742`.
Implementação: `2d610889210bd1e1085a0783310f99fdf2b3869a`; regressão final:
`89584b82de13ab80633cb63ae96591ed94930e44`. Alterações concorrentes preservadas.

- [x] R01 — Ler main e AGENTS; comparar o incremento anterior com alterações remotas antes de integrar.
- [x] R02 — Registrar plano de backend, frontend, design e testes antes de alterar o produto.
- [x] R03 — Integrar painel público de importações de recursos e tratamento de estados sem expor consultas, arquivos, erros brutos ou dados privados.
- [x] R04 — Exportar recursos por versão e seleções limitadas a 100 registros, com precisão, filtros, fontes, contagens e indicação de truncamento. Sem totais entre fases.
- [x] R05 — Preservar consultas compartilháveis e testar navegação nativa Voltar/Avançar, sem copiar parâmetros privados, favoritos ou credenciais.
- [x] R06 — Aprimorar ações mobile, leitura dos valores e estados independentes de carregamento/erro/recuperação nos três idiomas; fluxos verificados em 320/390/1440 pixels.
- [x] R07 — Testar API, precisão, limites, privacidade, integridade de versões, filtros e tradução, mantendo os gates anteriores.
- [x] R08 — Publicar no main e aprovar build TypeScript/Vite e cinco jornadas reais de navegador; corrigir sem remover gates.
- [x] R09 — Consultar o replay oficial PNCP: 6.677 registros/14 páginas, rollback por `invalid_resource_text`; resultado separado dos testes de software.
- [x] R10 — Consolidar checks, SHA testado, evidências e pendências neste TODO e no registro `docs/RESOURCE_STATUS_EXPORT_20260906.md`.

R03 cobre o painel de recursos. Não encerra a página cadastral mais ampla nem o
histórico paginado previstos em `docs/SPRINT_20260906_COVERAGE.md`.
R09 registra a inspeção do resultado real; não significa que a importação PNCP passou.

## Rodada anterior — precisão, recursos e compartilhamento

- [x] T01 — Consultar main, contrato AGENTS e pendências do roadmap.
- [x] T02 — Registrar o plano antes da implementação.
- [ ] T03 — Identificar o campo/registro que ainda bloqueia o replay oficial e concluir a importação reconciliada. A falha atual é textual; não inferir a causa nem contornar a alteração bloqueada.
- [x] T04 — Preservar a precisão monetária publicada e sua limitação, com regressões; eventos financeiros continuam no contrato próprio em centavos.
- [x] T05 — Tratar HTTP 204 somente no cenário PNCP explicitamente aceito, sem fabricar completude ou apagar registros anteriores.
- [x] T06 — Melhorar frontend de Obras e recursos: hierarquia, valores, estados e histórico; preservar lista e idiomas e verificar a interface compilada.
- [x] T07 — Implementar consultas compartilháveis e exportações públicas por recurso/versão e por seleção, sem conteúdo privado.
- [x] T08 — Testar API, integração, rollback, imutabilidade, formatação e tradução; manter o piso de cobertura.
- [x] T09 — Aprovar build e percursos de navegador em 320/390/1440 pixels, nos três idiomas.
- [x] T10 — Inspecionar consulta oficial delimitada executada e registrar sua falha separadamente da suíte sintética.
- [x] T11 — Registrar resultados, limitações e próximos passos na documentação desta entrega.
- [x] T12 — Confirmar publicação dos commits de código no main e execuções de CI correspondentes.

## Evidência da revisão integrada

- Suíte local: **537 testes Python aprovados**, **95,12% de cobertura de linhas**, piso de 85% mantido; **42 testes JavaScript aprovados**.
- Quality `34037366152` aprovada no commit `2d610889`.
- Quality `34037586194` aprovada no commit `89584b82`, incluindo regressão nativa de Voltar/Avançar.
- Cinco jornadas mantidas: consulta/favoritos/colaboração; revisão documental/privacidade; recursos/histórico; compartilhamento/exportação de versões; estado de importação/exportação de seleções.
- Artefato final browser `9990681235`, SHA-256 `a1b1d5592b5d1db0e081a3a10803e8b8fb5c31184a206782b1bb2421169b4245`.
- Runtime `34037366161`: PostgreSQL temporário e container read-only aprovados. Isso não é operação cloud.
- Fixtures de navegador são sintéticas, isoladas e não carregadas em produção. Não houve novo probe oficial nessas execuções Quality.

Histórico: T04/T05 passaram inicialmente com 478 Python/30 Node; compartilhamento
por versão entrou com 506 Python/36 Node. Os números acima são os do conjunto integrado.

## Dados oficiais — falha preservada

O replay `34034998849` recebeu 6.677 registros PNCP em 14 páginas e terminou com
`invalid_resource_text`; a transação foi revertida e não publicou novos contratos.
A causa exata do campo/registro ainda não foi comprovada. A alteração textual cuja
publicação foi bloqueada não integra a entrega e não foi contornada.
Dois registros de outras fontes foram aceitos em banco de verificação temporário.
Detalhes: `docs/reports/20260906-precision-reintake.json` e
`docs/RESOURCE_STATUS_EXPORT_20260906.md`.

## Próximo ciclo — dados e operação nacional

- [ ] N01 — Obter e importar a edição nacional 2025 do Censo Escolar; reconciliar registros e partições.
- [ ] N02 — Certificar cobertura cadastral de educação/saúde com denominadores e relatórios; presença nas UFs não é certificado.
- [ ] N03 — Ampliar instrumentos, metas, etapas, aditivos e pagamentos Transferegov; execução física/geometrias Obrasgov.
- [ ] N04 — Reconciliar fontes, estornos e destinatários; integrar PDDE/FNS respeitando granularidade e vínculos demonstrados.
- [ ] N05 — Avaliar extração/OCR em corpus oficial legitimamente obtido, com métricas por campo e revisão; completar quotas, cancelamento e retenção.
- [ ] N06 — Validar mapas/3D externos e panoramas opcionais em dispositivos limitados, sem bloquear o núcleo.
- [ ] N07 — Incorporar lockfiles revisados; validar acessibilidade assistiva, Safari/dispositivos físicos e desempenho.
- [ ] N08 — Validar hospedagem, HTTPS, publicação durável dos dados, atualização periódica, backups/restauração e rollback em ambiente público.
- [ ] N09 — Expandir grupos/tarefas/fotos e moderação apenas com privacidade, retenção e responsabilidade operacional.

## Critérios de aceite

Sem dados sintéticos em produção, sem vínculo de unidade por nome/proximidade,
sem soma de fases financeiras, sem LLM obrigatório e sem confundir testes com deploy.
Três idiomas e origem/referência temporal visíveis. Diferenciar ausência de dado,
indisponibilidade da fonte, falha de coleta e resultado de importação.
O projeto não está declarado integralmente concluído.
