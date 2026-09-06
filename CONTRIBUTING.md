# Contribuir

Contribuições de código entram sob AGPL-3.0-or-later, de documentação original sob CC-BY-4.0. Use commits com sign-off (`git commit -s`) para declarar o Developer Certificate of Origin: https://developercertificate.org/ . O sign-off declara o direito de submeter a contribuição, não transfere direitos autorais e não é assinatura criptográfica.

Abra uma issue descrevendo problema, fonte, comportamento esperado e como testar. Conectores novos exigem fonte oficial, condições de uso, amostra minimizada, perfil de campos, critérios de cobertura e falha. Dados pessoais e documentos originais não devem ser anexados a issues públicas. Não inclua senhas, tokens, rostos ou imagens de crianças/pacientes.

Execute os testes e o build. A aplicação deve continuar funcionando sem LLM. Precisão de dados vale mais que quantidade de conectores. Não relaxe validações para fazer um arquivo passar; documente a diferença e adicione um perfil testado.

Seja respeitoso. Divergência técnica e dados conflitantes são bem-vindos; perseguição, exposição pessoal e acusações sem verificação não são. Mantenedores podem remover conteúdo prejudicial. Revisão de contribuição não certifica a situação física de uma instituição.

## Publicação pelo conector GitHub

Falha de DNS ou autenticação do Git no terminal não determina as permissões do conector GitHub. Antes de declarar uma limitação, descubra as ações disponíveis na sessão e verifique as permissões efetivas no repositório. A disponibilidade pode variar entre conexões.

Quando as ações de escrita estiverem disponíveis, é possível publicar mudanças pela API Git Data, sem executar `git push` no terminal:

1. Leia a referência remota, a árvore atual, `AGENTS.md` e os arquivos que serão alterados. Verifique branches e PRs existentes antes de criar outro fluxo.
2. Use `create_blob` quando necessário e `create_tree` com a árvore-base atual. Preserve arquivos não alterados; arquivos textuais também podem ser enviados como `content` nas entradas da árvore.
3. Crie o commit com `create_commit`, usando como pai o commit remoto lido. Mantenha a mensagem descritiva e o sign-off aplicável.
4. Publique o commit na branch de trabalho com `update_ref`, mantendo `force=false`. Para uma nova branch autorizada, use `create_branch`. Não atualize `main` ou faça merge sem a autorização correspondente.
5. Se houver atualização concorrente, releia e compare o trabalho remoto antes de preparar outra alteração. Não use force push para contornar o conflito.
6. Consulte novamente a referência e os arquivos alterados. Reutilize o PR existente para esta implementação e reporte o SHA realmente publicado.

A criação de um commit isolado não significa que a branch foi atualizada. Publicação no GitHub também não comprova execução da CI, importação nacional ou implantação da aplicação. Registre cada resultado separadamente. Um ZIP ou bundle de uma sessão anterior não deve sobrescrever trabalho remoto mais recente sem comparação e integração explícitas.
