<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Minha região: descoberta municipal e contexto verificável

A aplicação oferece uma busca paginada por nome (insensível a acento/caixa), código
e UF. Ela consulta o diretório importado, não um serviço de geocodificação. Cidades
sem equipamentos carregados permanecem encontráveis; isso não implica falta de
serviços. O diretório é pequeno e limitado a 20.000 registros, com erro explícito
se excedido, para igualdade de normalização em SQLite e PostgreSQL. As tabelas
maiores de lugares e recursos são agregadas por SQL, sob um snapshot consistente.

## Contratos

`GET /api/territories/search?q=&state=BA&page=1&limit=12`: até 100 itens/página,
consulta de até 200 caracteres, somente UFs reconhecidas. `%` e `_` são literais.

`GET /api/territories/{codigo7}/summary`: instituição elegível, coordenada e fonte
são contados separadamente. Recursos com município do comprador são identificados
como tal, não como local de execução. Eventos financeiros são contados, nunca
somados entre fases. Não há associação a equipamentos por proximidade ou título.

A interface mantém diretório e resumo independentes, descarta respostas antigas
e oferece novas tentativas. O caminho até os registros financeiros e recursos
existentes foi preservado. A busca de serviços recebe município/tipo selecionados.
Nenhum dado de teste é importado pelo app. Nenhuma chamada de IA é necessária.

## Verificação

20 testes de backend/API cobrem filtros, limites, ausência, fontes mínimas,
contagens, ausência de efeitos colaterais e cinco SELECTs no resumo. Dois testes
Node verificam paridade de traduções e parâmetros. `ops/browser_regions.py`
exercita a aplicação compilada e API em banco sintético isolado nos três idiomas
em 320/390/1440px, incluindo falha de resumo/recuperação e passagem à busca.
A execução desse script e o SHA de CI devem ser registrados antes de declarar
aceite visual; escrever o teste não é executá-lo.
