<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Estado das importações consistente entre fusos

Fatia da Issue #2, em 15/10/2026. Base examinada:
`1733f9bddf2df8ad6210dacb0ce1da956c817b91`.

## Problema reproduzido

O histórico normalizava a data de início para UTC ao apresentar uma tentativa,
mas comparava o texto original ao filtrar `running` e `interrupted`.
Uma tentativa com fuso negativo podia desaparecer do filtro em andamento;
uma tentativa antiga com fuso positivo podia aparecer nele com estado
interrompido. No limite de seis horas, a leitura repetida do relógio também
podia selecionar um estado e devolver outro na mesma resposta.

As regressões iniciais produziram quatro falhas e dois controles aprovados.

## Correção

- Filtro e projeção usam o mesmo instante de corte por resposta.
- Datas são interpretadas pela mesma normalização UTC já usada na apresentação.
- O predicado SQL recebe apenas as exceções à comparação textual. Registros
  UTC comuns não são convertidos em uma lista de parâmetros por registro.
- A inspeção das exceções considera somente os estados em andamento e a
  fonte selecionada, com datas distintas.
- Contagens, paginação, fonte e estado devolvido permanecem coerentes.
- O resumo de cobertura compartilha o corte entre a última tentativa e o histórico.

## Evidência local

Python **3.14.8**, Node.js **24.20.0**, instalação Python pelo lock Linux com
37 versões conferidas e instalação web com `npm ci`. Nenhum pin ou gate alterado.

- Contrato de cobertura: **54 testes aprovados**, incluindo oito casos novos.
- Suíte Python integral: **1.895 aprovados**, zero falhas, erros ou skips;
  95 avisos registrados, sem supressão.
- Cobertura de linhas: **8.701/9.621**, acima do piso de 85%; não mede branches.
- Web: **243 testes aprovados**, zero skips, e build TypeScript/Vite aprovado.
- `compileall`, verificação dos runtimes e `git diff --check`: aprovados.

## Limites

As provas usam registros sintéticos e SQLite isolado. Não houve ingestão de
fontes externas, certificação nacional, alteração de dados de uma instalação,
execução de navegador, prova PostgreSQL/container ou deploy. A ordenação histórica
por texto de data é preservada; esta correção trata a classificação e os filtros.
`national_catalog_certified` continua falso. A Issue #2 permanece aberta.

`ingestions.started_at` permanece obrigatório (`NOT NULL`). O tratamento de
schema legado que permita nulos não faz parte desta fatia. A consulta inspeciona
as datas distintas das tentativas em andamento da fonte selecionada. Muitas
datas não canônicas cuja comparação textual discorde de UTC ainda podem formar
listas grandes e atingir o limite de parâmetros do banco; esse volume e uma
eventual migração para datas canônicas exigem prova de escala separada.

Os filtros atuais dos workflows não incluem os arquivos desta fatia; publicação
do commit, eventual execução remota e estas provas locais são resultados distintos.
