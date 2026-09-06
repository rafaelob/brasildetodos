<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Continuidade: obras e recursos versionados

## Publicação

Trabalho no `main`, sem PR novo nem force push. Base inicial:
`2131efbf222460b6c2a6b216a59b593f114a31c7`.

- `3763b8b017d195fa58e46466056f3dd52ae25b15`: inspeção limitada dos esquemas
  atuais e de uma amostra do PNCP; sem publicação de páginas brutas.
- `ae451b286fdc45d59ac081c2544d877e09c93fc4`: perfis oficiais de metadados,
  coleta verificada, histórico imutável, API, interface trilíngue e plano atualizado.
- `36aef1bcfd61d51298418722ea93968acf7ca4a4`: percurso de navegador da nova tela,
  integrado à CI sem remover os testes de colaboração e revisão documental.

## O que o cidadão passa a fazer

A tela **Obras e recursos** permite pesquisar objetos/títulos, filtrar por fonte
ou UF, abrir a referência e consultar as versões observadas pela plataforma.
Cada versão preserva os valores separados, sua fonte e os campos que mudaram.
O campo territorial informa se é município do comprador, UF principal ou local
não resolvido. Não criamos pinos de obras a partir do endereço do órgão.

Valores inicial/global/acumulado não são somados. Planos especiais não viram
convênios assinados, e valores previstos não viram pagamentos. O indicador de
receita do PNCP permanece distinguido. Reimportação sem alteração não cria uma
nova versão; ausência em uma consulta não apaga um registro.

## Software: verificações aprovadas

CI da revisão `36aef1bcfd61d51298418722ea93968acf7ca4a4`:
https://github.com/rafaelob/brasildetodos/actions/runs/34010614709

Backend, testes Node, TypeScript/Vite e navegador passaram. Na execução local,
446 testes Python passaram com 94,55% de cobertura de linhas; 28 testes Node
passaram. O piso de 85% foi preservado. Avisos de conexão da suíte legada não
foram ocultados e continuam separados da alegação de aprovação dos testes.

Artefato de navegador: `9982342210`, SHA-256
`94257034fd1ff8dc7daee30ef58904d4eb27596037dff55d66d67b708001b46a`.
A nova jornada verifica filtros por fonte/UF, busca literal do caractere %, duas
versões reais no banco de teste, valores distintos e pt-BR/en/es em 320, 390 e
1440 pixels, sem erros JavaScript ou overflow horizontal nos casos exercitados.
As capturas foram inspecionadas. Os dados desses testes são explicitamente
sintéticos; não são amostras publicadas da administração.

A CI também preservou os percursos anteriores: favoritos, contribuição privada,
revisão independente, publicação, revisão documental, exportação dos dados do
usuário, retirada e desativação da conta. Nenhum modelo é requerido para executá-los.

## Fontes reais: resultado separado, com falha explícita

Execução de coleta/importação:
https://github.com/rafaelob/brasildetodos/actions/runs/34010343797

Artefato `9982323950`, SHA-256
`112195def1d70918af09165e1908bf303a891fedcd793d1efa6a2506402f9faa`.
O relatório compacto está em `reports/20260906-resource-intake.json`.

### PNCP: coleta completa, importação recusada

A consulta de contratos publicados em 04/09/2026 recebeu **6.677 registros em
14 páginas**, totalizando **11.621.911 bytes**. As contagens e identidades da coleta
foram reconciliadas. Porém, na normalização, um valor acionou
`invalid_decimal_resource_amount`. A transação inteira dessa consulta foi desfeita:
**zero contratos PNCP foram publicados por essa execução**.

O relatório não identifica ainda o campo/registro responsável nem comprova sua
causa exata; não afirmar que é necessariamente um erro da fonte. O próximo passo
é obter diagnóstico minimizado de tipo/escala do campo, conferir seu significado
e criar uma representação explícita, caso a fonte admita precisão subcentavo.
Não arredondar, substituir por zero ou relaxar o piso para fazer a carga passar.
Uma tentativa de publicar um diagnóstico adicional foi bloqueada pela ferramenta;
o diagnóstico não integra os commits acima e não foi executado.

### Transferegov: um plano real importado e reconsultado

Foi descoberta uma identidade e feita outra consulta completa, filtrada por
`id_plano_acao=3221`. O plano **0903-003221**, ano 2020, foi importado como plano,
sem atribuição de município ou unidade. Custeio previsto R$ 30.000,00 e investimento
previsto R$ 80.000,00 permanecem distintos. Um novo processamento foi idempotente.
Não se trata de carga nacional de transferências, convênio assinado ou pagamento.

### Obrasgov: um projeto real importado e reconsultado

Consulta completa por `id_projeto_investimento=139010.35-00`:
**RIBEIRAO PRETO - SEDE - PEDIDO DE INTERVENÇÃO - 2026/02799**.
Situação declarada `Cadastrada`, UF principal SP, investimento previsto por fonte
estadual R$ 479.531,62. O nome da cidade no título não foi usado para fabricar
um vínculo municipal ou uma coordenada. O novo processamento foi idempotente.

### Aceite da API

Os dois registros aceitos foram consultados pela API, com filtros, histórico e
proteção dos endpoints documentais privados. Não foram criados eventos financeiros
nem vínculos automáticos com escolas/UBS. O artefato contém apenas metadados
normalizados e relatório, não o banco de usuários ou páginas brutas de fornecedores.

O status global da execução é **partial_with_explicit_failures** e o job terminou
com falha, corretamente: testes do software verdes não anulam a falha do PNCP.
Os dados aceitos estão em um banco de verificação temporário e em um artefato;
**não houve deploy público nem publicação durável de um catálogo nacional novo**.

## Pendências priorizadas

1. Diagnóstico de precisão PNCP e importação reconciliada da janela real; coleta
   incremental agendada, respostas vazias HTTP 204 e manutenção do histórico.
2. Download e ingestão nacional educacional 2025, ainda bloqueados nas tentativas
   anteriores, e certificação de partições sem usar presença de UF como conclusão.
3. Todos os módulos/tabelas Transferegov, contratos/documentos de referência,
   geometrias/execução física Obrasgov, beneficiários e eventos financeiros.
4. Reconciliação de fontes, valores e estornos; PDDE/FNS com granularidade original.
5. Corpus oficial de OCR, panoramas, mapa/3D externo, acessibilidade/dispositivos,
   lockfiles e operação contínua; domínio/HTTPS, atualização e backups no deploy.

O plano consolidado está em `ROADMAP.md`. Não há dependência de LLM adicionada,
reabertura de branch ou alegação de projeto integralmente concluído.
