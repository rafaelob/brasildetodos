<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Grupos privados de acompanhamento

Uma pessoa autenticada cria um grupo, convida membros, escolhe um lugar do
catálogo, abre uma tarefa e organiza a revisão independente de uma observação.
A API usa o banco real. Não existe backend simulado nem geração de dados cidadãos.
A interface está integrada; o aceite nativo e a API têm evidências distintas em `STATUS.md`.

## Permissões e fluxo

- Consulta pública do catálogo continua sem login. Grupos exigem sessão válida.
- Grupos não aparecem em busca pública; até revisores globais precisam ser membros.
- O responsável edita, convida, remove membros, transfere a responsabilidade ou
  arquiva. Membros criam/assumem tarefas e revisam entregas de outra pessoa.
- Convites individuais duram 48 horas, são revogáveis e de uso único. O código
  aleatório é retornado uma vez; só SHA-256 fica no banco. Não colocar tokens em
  URL, log, telemetria, favoritos ou exportação de conta.
- Toda escrita exige o controle CSRF existente e a revisão atual do grupo.
  Concorrência resulta em HTTP 409, nunca sobrescrita silenciosa.

A tarefa percorre aberta → em andamento → entregue → aceita ou complemento.
Liberação, reabertura e cancelamento são transições reais, com autoria e revisão.
A entrega exige observação própria, do mesmo lugar, ainda disponível, e confirmação
explícita de compartilhamento com o grupo. A revisão requer outra pessoa e nota.
**Aceitar no grupo NÃO aprova nem publica a observação na plataforma.**

## Retirada e privacidade

A projeção consulta a observação vigente. Retirada, retratação ou desativação do
autor remove a evidência da ficha do grupo e mostra indisponibilidade, mesmo se
a tarefa havia sido aceita. Saída/remoção retira entregas do membro e reabre as
tarefas atribuídas. Conta desativada tem tarefas/revisões próprias expurgadas,
grupo próprio arquivado e convites revogados; identificadores pseudônimos de
integridade/auditoria podem permanecer. Backups privados exigem a política de
retenção do operador e reconciliação das exclusões posteriores à cópia.

O exportador público mantém sua whitelist: nenhuma tabela de grupos é exportada.
A exportação da conta inclui somente suas associações, grupos de que é responsável,
textos de tarefas próprias e revisões próprias. Não inclui códigos nem nomes de
outros membros. Restauração SQLite revoga sessões e também convites da cópia.

## Limites e persistência

20 grupos por pessoa, 50 membros, 200 tarefas por grupo, 20 convites vigentes;
20 tarefas por página. Quotas são verificadas dentro da transação, após bloquear
o ator e comparar a revisão do grupo. Schema adicional versionado v1, criado sem
apagar dados. Versão desconhecida falha explicitamente. Não há LLM nem serviço
externo obrigatório. Convites não alteram o papel de revisor da plataforma.

## Rotas autenticadas

GET/POST `/api/groups`; POST `/api/groups/join`; GET `/api/groups/{id}`.
POST `/{id}/edit`, `/invites`, `/invites/{invite}/revoke`, `/leave`,
`/members/remove`, `/transfer`, `/archive`, `/tasks` e `/tasks/{task}`.
Todas as mutações sobre grupo existente incluem `expected_revision`.
Exportação/desativação usam as rotas de conta já existentes.

## Evidência deste incremento

32 regressões de API/SQLite reais: acesso, CSRF, expiração/revogação, uso único,
revisão independente, rollback, quotas, paginação, dupla disputa simultânea,
retirada/desativação, exportação própria e restauração. Fixtures sintéticos ficam
somente em testes temporários. A suíte auxiliar integrada passou com 834 testes
Python e 95,59% de cobertura; confirmação nos runtimes-alvo cabe à CI publicada.

## Operação

Grupo privado não é canal de denúncia, verificação oficial ou fila de atendimento.
O operador precisa definir retenção, suporte e tratamento de abuso antes de abrir
registro indiscriminado. Não registrar corpos de requisição. Usar HTTPS e cookies
seguros em produção. Esta implementação não declara hospedagem pública concluída.

## Aceite integrado posterior

Quality `34076805060` no código `8324b762` aprovou os doze percursos, incluindo
criação, convite, tarefa por busca de catálogo, observação própria, revisão
independente, recarga, retirada e saída, em pt-BR/en/es e 320/390/1440 pixels.
Contas e observações do ensaio são sintéticas e isoladas. O resultado não implica
deploy, moderação operacional ou um sistema de fotos já concluído.
