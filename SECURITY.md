# Segurança e privacidade

Não publique credenciais, dados pessoais ou passos de exploração em issues públicas. Use o canal privado de advisory do repositório se habilitado; caso contrário, abra uma issue apenas solicitando contato privado, sem detalhes sensíveis. Ainda não há SLA de resposta.

O núcleo tem limites de corpo JSON, sessões opacas com hash no banco, senha scrypt com salt, rate limit persistente, cookies HttpOnly/SameSite, checagem de Origin/header e separação de revisor. Cadastro público vem desligado. Não existe endpoint web para baixar URL arbitrária, receber PDF ou publicar foto.

Coletores possuem allowlist HTTPS, bloqueiam redirecionamentos não revisados, proxies de ambiente e endereços não públicos. Isso não substitui restrição de egress: execute download e parsing em processos/containers separados. PDFs não confiáveis devem ser processados em worker sem rede, não-root, filesystem temporário, memória/CPU/tempo limitados e sem credenciais.

Antes de produção: definir controlador/contato, políticas de privacidade e contribuição, retenção/exclusão/exportação, backups e teste de restauração, HTTPS, allowlist do domínio, logs sem conteúdo pessoal e revisão de dependências. Não habilitar cadastro amplo sem moderadores. Não confiar em `X-Forwarded-For` sem conhecer e configurar os proxies da implantação.

O rate limit usa o peer direto: atrás de proxy mal configurado, pode limitar todos conjuntamente. Isto é uma configuração de implantação a resolver, não motivo para confiar em headers arbitrários. API e aplicação devem permanecer na mesma origem. Favoritos ficam no dispositivo por padrão.
