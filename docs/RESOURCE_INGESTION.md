<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Recursos versionados: contratos, planos e projetos

## Contrato funcional

O catálogo recebe metadados de consultas completas e delimitadas, não uma alegação
implícita de todos os gastos públicos. A navegação **Obras e recursos** permite
buscar título/objeto, filtrar fonte/UF e consultar versões. A região de uma unidade
mostra recursos territoriais separadamente de vínculos documentais aprovados.

Três perfis baseados em OpenAPI efetivamente recebido em 06/09/2026:

| Perfil | Origem | Tipo e escopo publicados |
|---|---|---|
| `pncp_contracts` | `/api/consulta/v1/contratos` e `/contratos/atualizacao` | Contrato; município cadastrado da unidade compradora, **não local de execução**. |
| `transferegov_special_plans` | `/especiais/planos-acao-especiais` | Proposta/plano de ação; **não convênio assinado**. Município permanece não resolvido. |
| `obrasgov_projects` | `/obras/projeto-investimento` | Projeto/obra; UF principal declarada. Não gera coordenada ou município por aproximação. |

Esquemas: `https://pncp.gov.br/api/consulta/v3/api-docs`,
`https://api-publica.transferegov.gestao.gov.br/especiais/openapi.json`,
`https://api-publica.obrasgov.gestao.gov.br/obras/openapi.json`.
Inspeção inicial: execução GitHub Actions `34009291326`, artefato `9981954097`.
Amostra PNCP de 04/09/2026 declarou 6.677 registros; essa primeira página sozinha
não constitui importação completa. O resultado do processamento deve ser lido
separadamente nos artefatos de `Versioned official resource intake`.

## Invariantes

- JSON monetário lido diretamente com Decimal, sem passar por float; valores são
  convertidos a centavos exatos ou recusados. A UI preserva centavos com BigInt.
- Valor inicial/global/acumulado/plano não são parcelas somáveis. Nenhum desses
  perfis cria lançamento de pagamento nem altera a tabela `finance`.
- Receita marcada no PNCP é exibida como receita; ausência do indicador é desconhecida.
- Somente campos explicitamente permitidos são publicados. CPF/nome de fornecedor,
  contas bancárias, e-mails e texto complementar não são copiados indiscriminadamente.
  O objeto público pode mencionar pessoas e continua sujeito à política de dados.
- Não há associação automática a escola/UBS, sequer por nome ou proximidade.
- Município do beneficiário não é deduzido de `id_beneficiario` ou `id_ente`.
- Paginação precisa terminar e reconciliar total/identidades. Limite de páginas,
  resposta incompleta, JSON ambíguo, arquivo alterado ou conflito impedem a publicação.
- Uma execução inteira é transacional. Se uma linha falha, nenhuma alteração daquela
  consulta é publicada; um registro de falha separado permanece visível.
- Consultas completas são completas **para o filtro e momento observado**. Não
  certificam estado global em um único instante nem histórico nacional completo.
- Ausência em consultas posteriores nunca exclui/retrata recursos automaticamente.

## Versões e concorrência

`resource_revisions` é migração aditiva com chave única `(resource_id, revision)`.
A versão atual é atualizada junto com seu histórico na mesma transação. Bloqueio
por registro em PostgreSQL e unicidade impedem gravar duas revisões concorrentes.
Um conflito aborta a consulta; o operador deve reconciliar/reexecutar, sem force.

Mudança apenas de hash/página da consulta/data da coleta não gera alteração de
conteúdo. Mantemos a proveniência exata da primeira observação da versão.
PNCP usa data de atualização publicada (sem inventar fuso). Alteração no mesmo
instante ou regressão de versão é conflito. Planos e projetos usam versões de
coleta, claramente identificadas; não inventamos data oficial de atualização.
Recursos criados manualmente não são sobrescritos pelo importador.

## Execução

```sh
python -m bdt.resource_sync pncp_contracts \
  --database-url sqlite:///data/brasildetodos.db \
  --folder data/collections/pncp-20260904 \
  --start 20260904 --end 20260904 --page-size 500 --max-pages 20 --collect
```

Importe antes um cadastro IBGE real no mesmo banco. Para atualizar, use uma nova
pasta e `--updates` em janela declarada, revisitando intervalos conforme política
operacional. Reutilizar a pasta retoma apenas a mesma coleta, não atualiza a origem.
Sem `--collect`, verifica e importa somente os arquivos já existentes. Planos e
projetos aceitam `--year` e `--identity`; tamanho máximo de página é 200.

Fontes vazias que respondem HTTP 204 ainda são tratadas como falha de transporte
pelo coletor comum; não fabricamos um JSON vazio com hash de bytes inexistentes.
O conector deve ganhar um envelope explícito de resposta sem conteúdo antes de
usar janelas vazias numa rotina contínua. Há retomada por páginas da coleta, não
agendamento/checkpoint temporal automático de todos os períodos.

## API e privacidade

`GET /api/resources?q=&profile=&state=&municipality_id=&kind=&page=&limit=`.
`GET /api/resource-history/{id}?page=1&limit=10` retorna só metadados públicos das
versões. Não retorna texto extraído, contas, autores ou justificativas privadas.
A busca textual é case-insensitive conforme o banco, não um motor semântico.

O job `ops/resource_intake.py` verifica uma janela PNCP e duas consultas por ID,
com origem descoberta separadamente. Exporta metadados normalizados e relatório;
nunca envia o banco de usuários ou páginas brutas ao artefato público.

## Pendências específicas

Persistência e revisão de anexos em lote; todos os módulos e tabelas Transferegov;
beneficiário/IBGE com chave documental; geometrias e execução física Obrasgov;
reconciliação de pagamentos, estornos e aditivos; scheduler temporal com janela
sobreposta e relatórios de atraso; tratamento explícito de 204; análise de índices
e retenção do histórico. Os perfis são estritos: divergência exige evidência e
novos testes, não relaxamento silencioso de validações.
