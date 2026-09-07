<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Entrega de fotografias e reconciliação do produto

Base examinada: `84fde5f73dc8d84ef3ae72ce541f886ce96cb9f3`, Quality `34141612244` aprovada. Data: 2026-09-07. Trabalho somente no main, sem force push. Python 3.14.7 e Node 24.20.0 não são flexibilizados. O inventário de planos publicado não representa conclusão das funcionalidades.

## Entrega funcional atual

- [ ] M01 Implementar fotografia vinculada a observação própria, sem publicação automática.
- [ ] M02 Aceitar apenas JPEG/PNG reais, tamanho e pixels limitados; decodificar, aplicar máscaras opacas e reencodar removendo metadados. O original não é armazenado; o derivado tem hash próprio. Sem detecção automática de rostos ou promessa de anonimização integral.
- [ ] M03 Guardar derivado em armazenamento restrito, com cotas, identidade gerada pelo servidor e estado pendente. Metadados e bytes são consultados separadamente.
- [ ] M04 Exigir revisão por outra pessoa, confirmação explícita de privacidade e publicação somente se a observação associada também estiver aprovada. Revisão de fotografia não aprova observação.
- [ ] M05 Retirada e exclusão removem acesso público imediatamente; excluir bytes e texto na desativação da conta e retirada da observação. Documentar retenção de backups e impossibilidade de apagar cópias externas.
- [ ] M06 Interface pt-BR/en/es para anexar, visualizar, mascarar, enviar, revisar e retirar; falhas recuperáveis, teclado e celular. Nenhuma chave ou LLM obrigatório.
- [ ] M07 Testar arquivos reais gerados para ensaio, metadados, imagens inválidas, cotas, autorização, revisão independente, concorrência, exclusão e transações. Fixtures sintéticas permanecem apenas nos testes.
- [ ] M08 Exercitar frontend compilado e API persistente com dois usuários, nos três idiomas e em 320/390/1440 pixels, mantendo todos os percursos anteriores.
- [ ] M09 Publicar implementação no main, conferir CI da revisão e atualizar TODO/STATUS/matriz e issues sem fechar requisitos externos não comprovados.

## Reconciliação do restante, sem apagar escopo

As releases de saúde/recursos e escolas, instalação conjunta, grupos e acervo sintético de OCR já têm implementações publicadas. O TODO antigo ainda contém impedimentos de educação superados; sua revisão deve apontar evidências em vez de repetir downloads ou substituir trabalho existente.

Continuam distintos: atualização periódica e reconciliação nacional; tabelas financeiras Transferegov/PDDE/FNS e geometrias Obrasgov; corpus oficial anotado e fila documental operacional; panoramas e mapas externos; recuperação de conta e recursos de moderação; auditoria de dependências; dispositivos físicos e acessibilidade assistiva; implantação durável e recuperação operacional. A alteração de recuperação bloqueada anteriormente não será reenviada por outro caminho neste lote. A conexão de infraestrutura precisa ser confirmada antes de qualquer deploy com custos ou dados de usuários.

## Evidência exigida

Código, testes, publicação e aceite são resultados separados. Todo relatório informa revisão, runtimes reais, comando, saída e limites. Não marcar testado no runtime-alvo quando a execução foi auxiliar. Não publicar dados pessoais ou segredos em artefatos. Nova funcionalidade só recebe check completo com fluxo integrado aprovado; não criar botões ou endpoints simulados em produção.
