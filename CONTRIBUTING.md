# Contribuir

Contribuições de código entram sob AGPL-3.0-or-later; documentação original sob CC-BY-4.0. Use commits com sign-off (`git commit -s`) para declarar o Developer Certificate of Origin: https://developercertificate.org/ . O sign-off declara o direito de submeter a contribuição, não transfere direitos autorais e não é assinatura criptográfica.

Descreva problema, fonte, comportamento esperado e como testar. Conectores novos exigem fonte oficial, condições de uso, amostra minimizada, perfil de campos, critérios de cobertura e falha. Dados pessoais e documentos originais não devem ser anexados a issues públicas. Não inclua senhas, tokens, rostos ou imagens de crianças/pacientes.

Execute os testes e o build. A aplicação deve continuar funcionando sem LLM. Precisão de dados vale mais que quantidade de conectores. Não relaxe validações para fazer um arquivo passar: documente a diferença e adicione um perfil testado.

Seja respeitoso. Divergência técnica e dados conflitantes são bem-vindos; perseguição, exposição pessoal e acusações sem verificação não são. Revisão de contribuição não certifica a situação física de uma instituição.

## Trabalho no main

Por decisão explícita do proprietário em 05/09/2026, esta implementação trabalha exclusivamente em `main`. Não abrir nova branch ou PR para continuar a missão. Ler a referência mais recente, preservar trabalho concorrente, testar e publicar commits pequenos sem force push. Não sobrescrever versões remotas com ZIPs de sessões anteriores.

## Publicação pelo conector GitHub

Uma falha de DNS ou autenticação do Git no terminal não determina as permissões do conector. Verifique as ações e permissões efetivamente disponíveis.

Quando a escrita pela API Git Data estiver disponível:

1. Leia `main`, sua árvore, `AGENTS.md` e os arquivos afetados.
2. Use `create_tree` com a árvore-base atual e os arquivos novos ou modificados. Preserve os demais arquivos.
3. Crie o commit com `create_commit`, tendo o main lido como pai.
4. Publique em `main` com `update_ref` e `force=false`.
5. Se houver concorrência, releia e integre as mudanças; não force a referência.
6. Confirme novamente a referência, os arquivos publicados e os testes daquele SHA.

Commit criado sem atualização de referência não é publicação. Publicação não comprova CI, importação nacional ou deploy. Registre os resultados separadamente.
