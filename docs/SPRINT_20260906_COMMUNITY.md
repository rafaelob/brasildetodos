<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Lote: colaboração utilizável, evidências e operação verificável

Base inspecionada: `928534edd49dea24a3609c847a735f630ba72cdb`.
Somente main; não sobrescrever trabalho concorrente nem fazer force push.
Runtimes exigidos: Python 3.14.7 / Node 24.20.0. Nenhum LLM obrigatório.

## Prioridade

O main já integra Meus lugares, cobertura, histórico de recursos e mapa progressivo.
Este lote não os reimplementa. A próxima lacuna de produto é trabalho coletivo:
grupo privado persistente, convites com aceite, tarefas ligadas a lugares reais,
responsáveis, entrega de observação e conferência por outra pessoa. Observações
só se tornam públicas pelo fluxo moderado existente; grupos não publicam dados
oficiais nem concedem permissões de revisor.

## Checklist executável

- [x] C01 — Ler main/AGENTS/TODO e conferir bytes do snapshot remoto.
- [x] C02 — Registrar plano antes de alterar a aplicação.
- [ ] C03 — Persistência de grupos, convites temporários e membros; acesso por
  associação e mutações autenticadas/CSRF, controle de versão e quotas.
- [ ] C04 — Tarefas por lugar com assumir/liberar, entrega referenciando observação
  do próprio autor e conclusão independente apenas com observação aprovada.
- [ ] C05 — Integrar exportação/desativação de conta, saída/remoção de membros,
  encerramento de grupos e histórico mínimo sem conservar texto apagado.
- [ ] C06 — Interface completa pt-BR/en/es, criação/aceite de convite, membros,
  tarefas, filtros, estados de falha e recuperação, teclado e tela pequena.
- [ ] C07 — Testes de API real em banco temporário: permissões, convites expirados,
  transições, versão concorrente, evidência retirada e privacidade.
- [ ] C08 — Build e jornada de navegador nos runtimes exigidos em 320/390/1440px;
  preservar todas as jornadas existentes e corrigir problemas sem baixar gates.
- [ ] C09 — Conferir coleta oficial mais recente de recursos, nova tentativa de
  educação e mapa externo; distinguir reuso de artefato de coleta nova.
- [ ] C10 — Reconciliar TODO/ROADMAP/STATUS com evidências e inventário completo
  das frentes nacionais, documentos/OCR, panoramas, colaboração e produção.
- [ ] C11 — Publicar commits no main e confirmar revisão e resultados de CI.

## Critérios de aceite

Nenhuma rota fictícia, stub de persistência ou fixture de produção. Dados sintéticos
somente nos testes isolados. Grupo privado não é denúncia ou canal oficial.
Concluir uma tarefa significa conferir um procedimento de acompanhamento, não
certificar o serviço, a obra ou a acessibilidade. Revogação/retirada de uma evidência
precisa aparecer no grupo. Convites não carregam tokens na URL nem em logs.
Nenhum nome, conteúdo ou lista de membros privados entra em consultas públicas.

## Demais entregas não encerradas por este lote

Educação nacional e denominadores; módulos Transferegov, PDDE/FNS, pagamentos e
reconciliação; instalações duráveis e atualizações; corpus oficial OCR, quotas e
retenção; panoramas/fotos e licenças; acessibilidade assistiva/dispositivos;
hospedagem pública/HTTPS, backups e recuperação. Cada item só recebe check com
sua evidência, não por uma declaração de conclusão global.
