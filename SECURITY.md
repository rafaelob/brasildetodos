# Segurança e privacidade

## Reportar uma vulnerabilidade

Use o canal privado do GitHub: **Security → Report a vulnerability** (GitHub
Security Advisories) em
https://github.com/rafaelob/brasildetodos/security/advisories/new . Se o canal
não estiver disponível, abra uma issue apenas pedindo contato privado, sem
detalhes sensíveis.

Inclua versão/SHA, ambiente, impacto, passos mínimos de reprodução e sugestão
de correção. Não inclua dados pessoais, documentos reais, senhas, tokens ou
exploits prontos para uso público. Não há SLA de resposta; o projeto é
mantido por voluntários.

## Escopo atual

- autenticação, sessões, CSRF, rate limit e separação de revisor;
- vazamento de observações, fotos, documentos, originais ou excertos privados;
- path traversal, symlink, colisão de hash e acesso indevido ao store privado;
- SSRF, redirecionamento não revisado e limites de download dos coletores;
- exposição de PII em logs, exportações, issues ou artefatos;
- falhas em migrações, backup/restore e configuração de produção.

## Controles existentes

- Sessões opacas com hash no banco; senha scrypt com salt; cookies
  HttpOnly/SameSite; checagem de Origin/header; CSRF em escritas.
- Cadastro público desligado por padrão; revisor não aprova a própria
  contribuição.
- Sem endpoint web para baixar URL arbitrária, receber PDF ou publicar foto.
- Coletores com allowlist HTTPS, bloqueio de proxy/endereço não público e
  orçamento de bytes.
- Documentos e originais em store content-addressed privado, com SHA-256
  conferido a cada leitura; download apenas para revisor autenticado.
- Containers não-root/read-only quando aplicável, `cap_drop`,
  `no-new-privileges` e limites de memória/PIDs.
- Fila OCR sem bytes/texto; original conferido por hash antes do worker.

## Antes de produção

Produção exige decisões que este repositório não certifica sozinho:

- domínio, HTTPS/HSTS, origem e allowlist revisadas;
- segredos em gerenciador próprio, nunca no repositório;
- PostgreSQL durável com PITR, backup offsite e restauração ensaiada;
- política de retenção/expurgo, controlador/contato e revisão jurídica;
- moderação operacional e canal de recurso;
- logs sem PII, monitoramento, limites de recurso e rollback por digest;
- revisão de dependências, imagens e navegador;
- teste de carga e revisão de segurança independentes.

Docker Compose e `127.0.0.1` são ambiente local, nunca produção. O stack
PostgreSQL local usa `trust` somente na rede interna; não reutilize essa
configuração em uma rede exposta.

## Divulgação responsável

Pedimos um prazo razoável para correção antes de qualquer publicação. Não
teste sistemas de terceiros, não acesse dados de outras pessoas e não cause
interrupção de serviço. Relatos de boa-fé serão tratados com respeito.
