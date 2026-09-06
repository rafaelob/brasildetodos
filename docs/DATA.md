<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Fontes e integração

Esta versão é file-first: aceite de um arquivo não comprova cobertura nacional. Publicar a referência da edição, URL original, byte hash, contagem/partição e problemas. Não baixar todos os PDFs indiscriminadamente nem contornar autenticação/rate limits.

## IBGE

https://servicodados.ibge.gov.br/api/docs/localidades

Download da lista completa de municípios → import-ibge. O parser contempla microrregiao/mesorregiao/UF e regiao-imediata/regiao-intermediaria/UF. A conversão de códigos6 depende dessa tabela carregada. Catálogo nacional de estados observado no navegador de pesquisa; download nacional no ambiente de execução ainda não certificado.

## Inep

https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/censo-escolar

Perfil inicial exige CO_ENTIDADE, NO_ENTIDADE, CO_MUNICIPIO, TP_DEPENDENCIA e TP_SITUACAO_FUNCIONAMENTO; somente públicas ativas. Verificar o dicionário da edição antes de executar. CSV `;`, encoding explícito, membro ZIP escolhido pelo operador (sem extração livre em disco).

```bash
bdt import-inep data/censo.zip --member CAMINHO_EXATO_DA_TABELA.csv --encoding cp1252 --url URL_OFICIAL_DO_ARQUIVO --reference-date ANO_BASE
```

O comando aceita arquivo nacional; não corrige automaticamente mudanças de esquema entre edições. Endereço sem coordenadas continua consultável.

## CNES

https://apidadosabertos.saude.gov.br/cnes/estabelecimentos

```bash
bdt import-cnes data/cnes.json --root estabelecimentos --url URL_OFICIAL_DA_EDICAO --reference-date COMPETENCIA
```

A resposta examinada em 2026-09-05 possui `estabelecimento_faz_atendimento_ambulatorial_sus` (não `possui`) e `codigo_motivo_desabilitacao_estabelecimento`. Há registros de gestão MUNICIPAL com atendimento SUS NAO; gestão não certifica elegibilidade. O recorte é ambulatorial SUS declarado, não toda unidade pública ou todo hospital SUS. A referência individual data_atualizacao prevalece quando fornecida. Telefones não são garantia de atendimento.

A chamada sem filtros retornou cinco registros na inspeção. **Não existe aqui paginação nacional certificada.** Usar export oficial completo/perfis revisados; implementar paginação somente após documentação/experimento comprovarem parâmetros e condição terminal.

## Transferegov

https://www.gov.br/transferegov/pt-br/ferramentas-gestao/dados-abertos/download-dados
https://api-publica.transferegov.gestao.gov.br/

`import-transferegov` processa CSV com perfil JSON revisado pelo operador. Não é integração concluída de todas as tabelas ou módulos. O perfil tem columns para id, municipality_id, instrument_id, recipient, period, amount e phase/nature/perspective explícitos. Município deve estar no formato7 validado; quantia usa notação brasileira com centavos. Pré-convênio não é instrumento assinado; revisão do perfil deve filtrar condição/escopo antes da publicação.

```bash
bdt import-transferegov data/arquivo.csv --profile data/perfil-revisado.json --url URL_OFICIAL --reference-date DATA_REFERENCIA
```

Download antigo acessível não comprova atualização. Validar manifesto e migrações no portal. Novas APIs previstas para 2027 não são dependências prontas em setembro de 2026.

## PNCP e obras

https://www.gov.br/pncp/pt-br/acesso-a-informacao/copy_of_dados-abertos
https://api-publica.obrasgov.gestao.gov.br/

`pncp_contracts()` extrai metadados de resposta local com data[], não pagamentos. Nenhuma coordenada é inferida do comprador. Endpoint de paginação, revisitas de alterações, persistência integral e vínculos com obras são próximos incrementos. Obras conhecidas podem entrar via `import-places`, JSON canônico com fonte fornecida na CLI. A evidência para facility_id em finanças deve ser revisada.

## Finanças normalizadas

`bdt import-finance arquivo.json --url URL --reference-date REFERENCIA`. Contrato `MoneyEvent` em backend/bdt/domain.py. Campos obrigatórios: id, municipality_id, instrument_id, phase, cents (inteiro), period, recipient, perspective. source é substituída pela proveniência do arquivo real. relation_state=territorial por padrão. Natureza event/cumulative/estimate muda a agregação.

## Política de falha

Falhar por schema desconhecido, ID repetido, município não carregado ou correção financeira não reconciliada. Não substituir falta de dado por 0, coordenada aproximada ou promessa de vaga/consulta. Uma importação parcial conserva status provided_file_only. Resultados excluídos e falhas devem ser observados antes de disponibilização pública.
