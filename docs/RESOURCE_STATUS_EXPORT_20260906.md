<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Continuidade no main: importações compreensíveis e exportação pública

Data: 2026-09-06. Trabalho exclusivamente no `main`, sem novo PR ou force push.
Este registro distingue código, testes, coleta oficial e implantação pública.

## Entrega publicada

- `68a979062603bcd8d0604b9738cf961e2c1d3742`: plano R01–R10 registrado no TODO antes da implementação.
- `2d610889210bd1e1085a0783310f99fdf2b3869a`: painel público de importações de recursos e exportação limitada de seleções, integrado às funcionalidades remotas já existentes.
- `89584b82de13ab80633cb63ae96591ed94930e44`: regressão de navegação nativa Voltar/Avançar, preservando os testes de downloads, privacidade, erros, idiomas e responsividade.

Foram preservados os commits concorrentes `302e6b6c3b97bc29e2854836c8db3447e5ff5c1e` (compartilhamento e exportação por recurso/versão), `33a044276220b83819e87b3d76e7a43176ea7a25` (preparação correta dos painéis expansíveis no teste de downloads) e `042b3cd9acf051be30a59bd557cf75d73f02f60c` (plano mais amplo de cobertura). Esses trabalhos não são apresentados como implementação exclusiva deste incremento.

## Benefício e frontend

A pessoa pode compartilhar uma consulta pública filtrada, acessar um recurso por link, consultar suas versões e exportar uma seleção de até 100 registros. Filtros, contagem correspondente, quantidade exportada e truncamento ficam explícitos. O arquivo não é apresentado como cópia nacional completa.

O painel de importações mostra o que esta instalação carregou, a última tentativa e o último resultado concluído. Uma tentativa falha não transforma os registros anteriores em zero. Uma falha ao carregar o painel não bloqueia a busca; há estado independente de carregamento, erro e nova tentativa.

A interface mantém português, inglês e espanhol, estados vazios honestos, rótulos compreensíveis, foco visível e controles utilizáveis no celular. Links compartilháveis não copiam parâmetros privados, favoritos, sessões ou contribuições. Voltar/Avançar restaura as consultas exercitadas no teste.

## Backend e integridade

- API pública de estado de importação com projeção limitada: sem consultas internas, caminhos de arquivos, traceback ou dados de usuários.
- Exportação de seleção em JSON, CSV e texto com limite de 100 registros, critérios e indicação de truncamento.
- Preservação do exportador por recurso e versão histórica; nenhuma substituição do contrato remoto já implementado.
- Valores exatos e referências preservados, inclusive frações de centavo admitidas pelo perfil cadastral PNCP. Não há soma de fases financeiras nem criação de pagamentos a partir de contratos.
- Verificação de integridade de versões; inconsistência bloqueia a exportação em vez de misturar versões.
- Projeção pública limitada: sem conteúdo documental privado, contas, sessões, observações privadas ou justificativas internas.
- Proteção de células CSV contra interpretação como fórmula. JSON conserva a representação textual exata nos campos exportados.

O núcleo não depende de LLM e esses fluxos não requerem chamadas a provedores de IA.

## Evidências executadas

### Suíte integrada local

Após incorporar as alterações remotas: **537 testes Python aprovados**, **95,12% de cobertura de linhas**, preservando o piso de 85%; **42 testes JavaScript aprovados**. São medições do conjunto integrado desta revisão, não uma certificação universal de qualidade ou de dados nacionais.

### CI da implementação

Código: `2d610889210bd1e1085a0783310f99fdf2b3869a`.
Quality: https://github.com/rafaelob/brasildetodos/actions/runs/34037366152
Resultado confirmado: backend, testes Node, TypeScript/Vite e os cinco percursos de navegador aprovados.

Runtime: https://github.com/rafaelob/brasildetodos/actions/runs/34037366161
Resultado confirmado: PostgreSQL temporário e container real em filesystem somente leitura com dados temporários. Não equivalem a implantação cloud.

### CI da regressão Voltar/Avançar

Código/teste: `89584b82de13ab80633cb63ae96591ed94930e44`.
Quality: https://github.com/rafaelob/brasildetodos/actions/runs/34037586194
Resultado confirmado: backend, testes Node, build TypeScript/Vite e navegador aprovados.

Percursos mantidos na CI:
1. `ops/browser_smoke.py`: busca, favoritos e colaboração.
2. `ops/browser_extended.py`: documento privado, proposta de vínculo, revisão independente, publicação e ciclo de privacidade.
3. `ops/browser_resources.py`: filtros, histórico e separação monetária.
4. `ops/browser_resource_sharing.py`: links públicos, exportação por versão e precisão.
5. `ops/browser_resource_status.py`: estado de importação, downloads de seleção, recuperação de falha e navegação Voltar/Avançar.

Os testes usam interface compilada e API real em banco temporário com fixtures explicitamente sintéticas. Foram exercitados pt-BR/en/es e larguras de 320, 390 e 1440 pixels. Isso não comprova Safari em aparelho físico, leitor de tela, conformidade WCAG integral, tiles/3D externos nem comportamento sob carga pública.

Artefato de navegador da revisão final: `9990681235`, SHA-256 `a1b1d5592b5d1db0e081a3a10803e8b8fb5c31184a206782b1bb2421169b4245`.
Artefato de backend: `9990664003`, SHA-256 `d2bf76e7c14b1534287b41216bc111960707f89150e177e120c23a465e5d2e28`.
Build web: `9990656330`, SHA-256 `14d9f470aa0459b4ef0ce4073b09d5edb59b999ecf49eb58b91f525c86ecb683`.

O probe de fontes oficiais não foi executado nessas suítes Quality. Aprovação do software não representa aprovação de uma nova carga oficial.

## Replay oficial: resultado separado

Execução anterior inspecionada: https://github.com/rafaelob/brasildetodos/actions/runs/34034998849
Artefato `9989939474`, SHA-256 `44eadf4b7d587833f25ceb9f376ecf3129140ef6217a11cc26cc4721c821bd97`.

A consulta PNCP recebeu 6.677 registros em 14 páginas. Após a correção da representação monetária, a normalização encontrou `invalid_resource_text`; a transação permaneceu revertida, sem novos contratos publicados por essa execução. Isso não identifica sozinho qual campo ou registro causou a falha, nem atribui culpa à fonte. A alteração textual cuja publicação foi bloqueada não integra esta entrega e não foi contornada.

Dois registros delimitados de outras fontes foram aceitos no ensaio: um plano de ação de transferências especiais e um projeto Obrasgov, com valores e escopo preservados. São dados de teste de integração em banco temporário, não uma carga nacional de obras ou transferências.

## TODO concluído neste recorte

- [x] Plano registrado no main antes da implementação.
- [x] Integração das alterações remotas sem sobrescrita.
- [x] Painel de importações de recursos e projeção pública.
- [x] Exportação de seleções com limite, fontes, precisão e truncamento.
- [x] Compartilhamento e navegação preservados e testados.
- [x] Interface responsiva e três idiomas nos fluxos exercitados.
- [x] Testes de API, JavaScript, build e cinco jornadas de navegador.
- [x] Publicação dos commits de implementação no main e consulta das execuções da CI.
- [x] Registro separado da falha do replay oficial.

A implementação não encerra por si só o plano U de `SPRINT_20260906_COVERAGE.md`: cobertura cadastral detalhada por UF e histórico paginado de todas as importações têm escopo mais amplo que o painel de recursos entregue.

## Próximas pendências

- Diagnosticar legitimamente o campo textual PNCP e concluir a importação reconciliada, sem relaxamento silencioso de validações.
- Obter/importar educação nacional 2025 e reconciliar cobertura de escolas e saúde com denominadores adequados.
- Ampliar Transferegov/Obrasgov, documentos, eventos financeiros, PDDE/FNS e reconciliação entre fontes.
- Avaliar extração/OCR em corpus oficial e completar quotas, retenção e revisão operacional.
- Validar mapas/3D/panoramas externos, desempenho, acessibilidade assistiva e dispositivos físicos.
- Revisar lockfiles, operação contínua, publicação durável, HTTPS, backups e rollback.
- Implantar uma instância pública real; não há deploy público comprovado nesta entrega.
