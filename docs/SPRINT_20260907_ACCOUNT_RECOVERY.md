<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Recuperação de conta sem serviço externo obrigatório

Base funcional: `4310c7e735e4593946791876d34943c56c6d9d40`.
Continuidade de U04: a implementação abaixo fecha recuperação com códigos
previamente guardados, não o recurso de moderação, nem recuperação por e-mail.
Somente main; Python 3.14.7 e Node 24.20.0; nenhuma mudança nas releases de dados.

- [ ] A01 Criar registro de recuperação com hash, prazo e versão; código aleatório retornado somente ao titular autenticado após confirmar a senha.
- [ ] A02 Permitir revogação e rotação, invalidando todo código anterior; não incluir códigos em URLs, logs, exportações gerais ou localStorage.
- [ ] A03 Recuperar senha com nome de usuário e código válido; operação atômica de uso único, sem auto-login, com revogação das sessões e códigos anteriores.
- [ ] A04 Resposta uniforme a credencial inválida, prazo expirado ou conta inexistente/desativada; limitação de tentativas e CSRF existentes preservados.
- [ ] A05 Integrar expurgo dos códigos à desativação; proteger contra corridas de recuperação e invalidação de conta.
- [ ] A06 Interface pt-BR/en/es para gerar, guardar, revogar e usar o código; confirmação da nova senha, feedback acessível e apagamento do segredo ao sair.
- [ ] A07 Testar rollback, replay, expiração, alteração de papel, exclusão, sessão concorrente, origem, quotas e campos privados; manter as suítes anteriores.
- [ ] A08 Executar fluxo completo no navegador com conta sintética isolada e persistência real; build e CI nos runtimes-alvo.
- [ ] A09 Atualizar o plano completo, documentação e evidências no main somente após aceite.

Escolha de produto: código de recuperação de alta entropia, de uso único, salvo
pelo próprio usuário antes da perda da senha. Sem código previamente preparado,
não existe promessa de recuperação automática. Não adicionar perguntas pessoais
ou senhas padrão. Prazo e perda do código devem ser informados antes da geração.
Nunca tratar o código como uma prova de identidade civil.

Referências de implementação: documentação oficial Python `secrets` e OWASP
Forgot Password Cheat Sheet (consultadas em 07/09/2026). Aplicamos tokens fortes,
uso único, prazo, armazenamento não reversível e invalidação de sessões; sem
serviço de e-mail configurado, não anunciamos envio de mensagens ou notificações.
