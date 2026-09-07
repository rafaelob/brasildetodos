<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Auditoria e execução — 07/09/2026

Base inspecionada: `3dd1af52e8e89faacf254d8cf637163e97db13b8`. Snapshot Actions `10023353122`, SHA-256 `57b96078a1030feaca70c583c22578ee70e17692662b47a47625db8f680e609e`. Somente `main`, sem force push; preservar trabalho concorrente. Python 3.14.7 / Node 24.20.0.

## Fontes e divergências encontradas

Foram recuperados AGENTS.md, TODO.md, planos de sprints, matriz de funcionalidades, plano mestre e issues abertas #2–#5. O plano histórico Conferido — Pacote unificado é uma fonte de requisitos, não evidência de implementação. Seus recortes municipais, idioma único e sugestões de vínculo por proximidade foram explicitamente substituídos pelo contrato nacional/trilíngue e de proveniência do usuário. Mapa/3D, imagens, participação e documentação continuam parte do escopo.

O `TODO.md` ainda descreve TLS/Inep como bloqueio, mas as releases escolares e a instalação conjunta já foram publicadas. O plano mestre está no GitHub (commit `3dd1af52`), apesar de o resumo anterior não ter confirmado isso. As issues #2–#5 preservam a situação da PR inicial e misturam funcionalidades entregues com partes ainda abertas. Não fechar essas issues inteiras por causa de um incremento parcial.

Há 352 entradas no snapshot, incluindo diretórios; isso não é uma contagem de funcionalidades. Não usar checkboxes, número de testes ou presença de arquivos como percentual de produto concluído.

## Situação confirmada no início

- Catálogo de saúde e recursos distribuído em `public-data-20260906-v1`.
- Catálogo escolar 2025 distribuído em `education-2025-20260907-v1`.
- Instalador combinado e aceite `34131239400` já publicados; não recriar uma terceira implementação.
- Pesquisa, favoritos/histórico/comparação, região, cobertura, exportações, documentos privados/revisão, observação guiada e grupos implementados. Revisão-base aprovada em Quality `34134352676`.
- Recuperação de conta: somente plano publicado. Não há módulo/rotas/componentes correspondentes na árvore-base. Código mencionado em resumos anteriores não é entrega remota.
- Corpus de OCR versionado é sintético. Não renomeá-lo para corpus governamental.
- Fotografias e panoramas continuam ausentes do fluxo de produção; `/api/config` anuncia `photo_uploads: false`.
- Não foi identificada instância pública implantada ou certificado de acessibilidade/dispositivos físicos.

## Frentes restantes, sem apagar os planos existentes

1. Conta: recuperação com segredo previamente guardado, rotação/revogação/expiração, invalidação de sessões e interface completa. Recurso de moderação e retenção são entregas separadas.
2. Dados: reconciliação por município/UF, dicionários, nova competência CNES, atualização incremental com revisitas, publicação no banco operacional sem perda de contas/contribuições e indicadores de atraso.
3. Recursos: demais tabelas Transferegov, execução física/geometrias Obrasgov, PDDE/FNS, anexos e reconciliação de eventos/estornos/beneficiários sem dupla contagem.
4. Documentos: corpus oficial revisado e anotado, métricas por família/campo, tabelas multipágina, fila persistente com quotas/cancelamento/retentativas/isolamento e retenção/expurgo.
5. Colaboração: fotografias privadas e revisão/redação, exclusão de derivados, panoramas opcionais, contestação de moderação e políticas de abuso/retenção.
6. Experiência: basemap externo e 3D com dados/licenças identificados, ausência de WebGL, auditoria integral de estados/idiomas/teclado/contraste; leitores de tela e aparelhos físicos continuam exigências distintas.
7. Operação: infraestrutura efetivamente conectada, banco/documentos duráveis, HTTPS, atualização, backups/restauração/rollback, desempenho nacional medido, auditoria de dependências/imagens e plataformas adicionais.

## Lote executável imediato

- [x] R01 Ler base real, contrato e issues; confirmar planos publicados e divergências.
- [ ] R02 Inventariar checkboxes de todos os documentos com caminho/linha e separar histórico de estado corrente; preservar a redação original.
- [ ] R03 Implementar recuperação integrada: código de alta entropia, armazenamento não reversível, uso único, prazo e reautenticação.
- [ ] R04 Tratar concorrência com login, rotação e desativação; rollback integral e proteção de sessões/segredos.
- [ ] R05 Implementar interface pt-BR/en/es, confirmação de guarda, rotação/revogação, uso sem auto-login, estados de erro/cancelamento e limpeza ao sair.
- [ ] R06 Testar rotas reais, erros, CSRF, limites, concorrência, expiração, não exposição e restauração de backups.
- [ ] R07 Executar frontend compilado e percurso completo com duas sessões reais em 320/390/1440 e três idiomas, sem remover jornadas anteriores.
- [ ] R08 Confirmar commits no main e CI da própria revisão; atualizar TODO, planos e issues com evidências, não previsões.

## Critério de registro

Publicação, regressão de software, coleta oficial e deploy são resultados separados. Fixtures sintéticas são permitidas para testes de falha, nunca para preencher produção ou medir acurácia documental oficial. Dependência externa não configurada permanece bloqueio explícito. Toda nova execução deve registrar comandos, revisão, runtimes, resultado e limites. Não marcar uma tarefa concluída antes de receber a evidência correspondente.
