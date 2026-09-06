<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Precisão cadastral e ausência explícita de resultados

## Contrato da fonte

Manual de consultas PNCP, versão 1.0, páginas 37–38:
https://www.gov.br/pncp/pt-br/pncp/copy_of_manuais/ManualPNCPAPIConsultasVerso1.0.pdf/@@display-file/file

`valorInicial`, `valorGlobal`, `valorAcumulado` e `valorParcela` admitem até quatro
casas decimais. O importador representa os três primeiros; não cria lançamentos
financeiros a partir desses metadados. HTTP 204 é uma resposta sem conteúdo.

## Representação retrocompatível

Valores exatamente representáveis em centavos mantêm os campos `*_cents` e não
recebem novos atributos. Assim, reimportar os mesmos registros não altera seus
fingerprints somente pela atualização do extrator. Para uma fração de centavo,
o respectivo campo de centavos é nulo e `attributes.precise_amounts` conserva a
quantia em texto decimal canônico de três ou quatro casas, por exemplo
`{"initial": "100.0001"}`. Zero permanece zero; desconhecido permanece nulo.

A interface formata esses valores via partes de Intl e aritmética BigInt, sem
converter o montante completo em Number e sem arredondar. Exibe aviso específico.
Entradas não finitas, floats já arredondados, valores negativos, escala não
admitida e valores fora dos limites continuam recusados. Os eventos financeiros
mantêm sua validação estrita de centavos; esta mudança não flexibiliza pagamentos.

O manifesto da importação registra contagens `subcent_records` e
`subcent_fields`, não nomes de fornecedores nem dados pessoais para diagnóstico.

## HTTP 204

Somente a primeira página, sem registros prévios, em consultas PNCP de contratos
ou atualizações permite terminar a coleção como vazia. Os bytes vazios têm hash
calculado, código HTTP preservado e marcador `http_204_no_content`. A verificação
da coleção confere esses campos. Não inferir que contratos anteriores desapareceram.
204 após páginas com dados, corpo não vazio, 200 vazio ou outro provedor não passam.

## Evidência local

32 testes comportamentais adicionados. Suíte completa: 478 Python aprovados,
95,05% de cobertura de linhas; 30 testes Node aprovados. A causa do registro que
bloqueou a carga anterior não foi determinada apenas por consultar o manual.
A execução oficial delimitada precisa registrar resultado próprio; nenhum deploy
ou certificado nacional decorre desta alteração.
