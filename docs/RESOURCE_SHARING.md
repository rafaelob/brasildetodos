<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Compartilhamento público e leitura dos recursos

## Experiência

Obras e recursos tem hierarquia por fonte/tipo, filtros agrupados, quantidade da
consulta, limpar filtros e estados separados de carregamento, falha e ausência.
Texto de ausência não afirma que obras ou investimentos não existem. Controles
adaptam-se ao celular, com labels explícitos e sem obrigar uso de mapa ou login.

A ação Compartilhar constrói uma URL somente com busca, perfil de fonte, UF,
município explícito, identificador opcional e idioma. Esses critérios ficam
visíveis antes de copiar. A URL não reutiliza parâmetros antigos, sessões,
favoritos ou GPS. O texto digitado vira parte do link escolhido pelo usuário;
isso é avisado. Sem clipboard, o campo selecionável continua utilizável.

Abrir o link reconstitui a consulta ou mostra uma ficha de recurso. Critérios
são validados e limitados. Nenhum URL de API externa vem do link. Dados atuais
podem mudar entre visitas; compartilhar uma consulta não congela o catálogo.

## Exportação

GET /api/resource-export/{id}?format=json|csv|text&locale=pt-BR|en|es
Parâmetro opcional revision=N recupera uma versão específica. A resposta traz
uma projeção pública e limitada, origem, referência, coleta, hash de conteúdo e
aviso. Valores decimais são strings exatas; fases não são somadas. Não há
consultas a usuários, observações, links de revisão ou documentos privados.

O export atual recusa divergência entre o ledger e o registro; não mistura
versões. Em uma versão histórica, a fonte é a daquela versão. Sem ledger, a
revisão é explicitamente nula. CSV protege células interpretáveis como fórmula;
o JSON é a opção para recuperar o texto original sem esse escape de planilha.
Identificadores e nomes de campos no formato tabular permanecem estáveis.

## Validação

28 testes Python de exportação, seis testes Node de roteamento/idiomas e um
percurso de navegador adicionado à CI preservam as verificações anteriores.
Suíte local após os ajustes: 506 Python e 36 Node; 94,96% linhas, piso 85%.
Build e percurso de navegador desta revisão precisam de sua própria execução.
Fixtures são sintéticas e não fazem bootstrap da aplicação normal.

## Limites

Não é exportação em massa de todo orçamento nem de toda consulta paginada.
Não há URL pública de produção criada por essa funcionalidade. Resultados de
fontes reais e a cobertura nacional continuam sendo critérios separados.
