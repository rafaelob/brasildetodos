<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Visitas guiadas e cópias de observações

## Entrega

Na ficha de escola, saúde ou obra, Comunidade oferece Registrar visita guiada.
São quatro perguntas observáveis por tipo, com Sim/Não/Não sei sem seleção padrão,
data, descrição e consentimento. A pessoa confere uma prévia e envia pelo fluxo
`POST /api/observations` que já existe. Não exige LLM, GPS, fotos ou mapa.

O assistente de preenchimento é cliente, não um laudo nem uma verificação do
servidor. Perguntas e respostas, identificador de roteiro, idioma e contexto
cadastral são convertidos em texto legível com no máximo 1.200 caracteres. O
servidor persiste esse texto como observação cidadã sujeita à revisão existente.
Não adicionamos um novo contrato de dados à API central nesta entrega.

Os textos de roteiro v1 são do Brasil de Todos, não exigências governamentais ou
itens de um contrato. Observar identificação, placa, aviso ou barreira não comprova
funcionamento, qualidade, segurança ou acessibilidade. Somente área pública permitida.
Imagem histórica permanece no modo de referência de imagem, não vira visita atual.

## Publicação e privacidade

O envio permanece privado e pendente. Outra pessoa revisa a publicação. O autor
pode retirar a contribuição; ela deixa de aparecer nas consultas públicas.
Não se alteram cadastro oficial, autenticação, CSRF, limites ou papéis existentes.
Não há chamadas simuladas no percurso de produção nem preenchimento automático de
respostas. O rascunho fica somente na memória da tela, sem envio até confirmação.
Erro de envio conserva o texto e orienta conferir Minhas contribuições antes de
repetir, pois uma falha de comunicação não prova ausência de gravação no servidor.

As observações aprovadas exibem Baixar observação publicada. A cópia JSON é uma
projeção dos dados já recebidos, com origem de referência, data, corpo e estado da
consulta. Não copia author_id, nota privada de revisão, consentimento ou atributos
arbitrários. Não é certificado criptográfico nem prova de situação atual do local.
Arquivos já baixados não podem ser revogados; remover a publicação afeta novas
consultas, não uma cópia que o visitante já recebeu.

## Limite explícito e decisão de escopo

A tentativa de alterar a API central e seu modelo foi bloqueada pela ferramenta.
Esses arquivos foram preservados, e as novas rotas de guia/exportação não foram
publicadas nem instaladas indiretamente. A funcionalidade entregue utiliza somente
o contrato existente. Assim, não se alega validação transacional de versão do
roteiro, snapshot tipado ou bloqueio de envio por mudança concorrente no cadastro.
Uma revisão desse contrato é uma pendência distinta, não um comportamento simulado.

## Testes

`web/tests/visit.test.mjs`: traduções, perguntas, obrigatoriedade, orçamento textual,
identificadores, ausência de respostas implícitas e projeção pública.
`backend/tests/test_guided_text_compatibility.py`: gravação real em SQLite, fila
privada, exportação pessoal, revisão independente, consulta pública e retirada,
sem mudar a API existente.
`ops/browser_guided_visit.py`: aplicação compilada, sessão real, API, persistência,
revisão, cópia JSON e retirada nos três idiomas e em 320/390/1440 px. Dados sintéticos
são isolados no teste e jamais usados para inicializar o catálogo de produção.
Resultados e SHAs estão no registro do lote; script escrito não significa teste aprovado.
