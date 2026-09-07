<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Aceitação visual de catálogo publicado

`ops/browser_public_catalog.py` recebe um catálogo público e um SHA-256 de
manifesto selecionado pelo operador. Congela os arquivos em área privada,
verifica-os e instala um banco temporário novo; não modifica os registros de
origem nem abre uma instalação com usuários. Somente os nomes de arquivos
previstos no formato são copiados. Arquivos privados adicionais ficam de fora.

O ensaio seleciona até dois registros elegíveis do dataset solicitado de forma
determinística: um sem coordenadas e um com coordenadas, quando existirem.
Ausência de qualquer grupo não é preenchida artificialmente. Uma seleção vazia
falha, em vez de usar outro dataset ou fabricar exemplos.

O navegador utiliza o frontend compilado e a API local real, sem interceptar
ou substituir respostas. Verifica pesquisa, ficha, fonte, referência, exportação
JSON exatamente igual ao cadastro, ausência de coordenadas preservada, favoritos
após recarga e reflow em 320/390/1440 pixels para pt-BR/en/es. Não cria contas,
observações ou registros. Preferências de favoritos existem só no navegador
temporário. O mapa não é ativado; nenhuma requisição externa é necessária.

O workflow `Published data and OCR acceptance` agora executa também esse percurso
sobre a release v1 fixada em `data/releases/`, com Python 3.14.7, Node 24.20.0 e
locks existentes. Os doze percursos sintéticos de regressão na Quality continuam
independentes e não são removidos. Os testes unitários deste ensaio usam fixtures
sintéticas; a execução de aceite da release usa os registros efetivamente publicados.

Os relatórios incluem a revisão, hashes e IDs públicos selecionados. Capturas
mostram lugares do catálogo público, nunca cidadãos, pacientes ou contas reais.
Uma falha no percurso deve permanecer registrada como falha. Esta validação
não certifica cobertura nacional, atualidade do atendimento, acessibilidade
assistiva, dispositivos físicos, mapas externos ou implantação pública.

A primeira tentativa local foi bloqueada pela política de navegação do Chromium
(ERR_BLOCKED_BY_ADMINISTRATOR). Não foi contornada com páginas fabricadas; o
percurso deve ser executado no runner, registrando sua conclusão independente.
