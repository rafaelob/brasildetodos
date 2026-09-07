<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Abertura de fichas: cancelamento e respostas atrasadas

A revisão da aplicação identificou que a proteção da resposta bem-sucedida não
cobria erros e finalizadores de requisições antigas. A abertura de ficha deve ser
independente do carregamento da busca e de mutações de conta ou observações.

- [ ] L01 Reutilizar createLatestTask para ficha e histórico sob a mesma operação.
- [ ] L02 Cancelar ao navegar e impedir sucesso, erro ou finalizador atrasado de alterar a tela atual.
- [ ] L03 Oferecer cancelamento por teclado e rótulos pt-BR/en/es sem bloquear a busca.
- [ ] L04 Testar concorrência e criar percurso com API real e falhas temporais controladas, mantendo os doze percursos existentes.
- [ ] L05 Publicar no main e aprovar build e navegador em Python 3.14.7/Node 24.20.0.

Os registros do ensaio de concorrência são sintéticos e isolados. A proteção de
respostas atrasadas não substitui a validação separada da interface sobre os
catálogos governamentais publicados. O aceite de dados reais não injeta respostas
fabricadas na API. Nenhum check será concluído apenas pela existência do teste.
