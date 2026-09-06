<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Carga nacional de educação

O comando `python ops/education_bulk.py --year 2025` descobre a distribuição
ZIP na página oficial do Censo Escolar, e não assume uma URL de arquivo eterna.
A página foi consultada nesta implementação e apresenta a edição 2025 atualizada
em julho de 2026. Fonte: https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/censo-escolar

## Publicação e abrangência

O processamento roda fora das requisições web e publica um pacote minimizado
compatível com `python -m bdt.catalog_release verify <diretório>` e `install`.
Consulte `python -m bdt.catalog_release --help` para os argumentos exatos.
O banco interno, os originais e as tabelas de alunos, docentes e turmas não são
incluídos no artefato público. Não há dependência de LLM ou OCR para CSV.

1. Carregar os identificadores territoriais oficiais; alternativamente reutilizar
   `--territory-snapshot arquivo.db`, validando os identificadores e preservando
   as datas e hashes originais. Reutilizar um snapshot não é fazer uma coleta nova.
2. Aceitar exatamente um link HTTPS no host oficial para o ano selecionado.
3. Aplicar orçamentos de bytes, quantidade de membros e razão de compressão.
   Nenhum caminho de ZIP é extraído diretamente para o sistema de arquivos.
4. Selecionar somente tabelas escolares com cabeçalhos já interpretados. O perfil
   atual requer CO_ENTIDADE, NO_ENTIDADE, CO_MUNICIPIO, TP_DEPENDENCIA e
   TP_SITUACAO_FUNCIONAMENTO. Outro perfil exige revisão explícita e testes.
5. Validar encoding de todo o conteúdo, não apenas de cabeçalhos ASCII. UTF-8 e
   Windows-1252 são lidos estritamente, sem substituição silenciosa de caracteres.
6. Percorrer todas as linhas antes da transação: IDs, duplicidade entre tabelas,
   municípios, ano quando publicado e concordância de UF. Códigos desconhecidos
   de elegibilidade param a carga; não são convertidos em exclusões silenciosas.
7. Exigir presença de escolas elegíveis nas 27 UFs para o comando nacional. A
   presença das UFs é verificação de partições, não comprovação de completude.
8. Importar transacionalmente. Sem coordenadas, a escola continua encontrável;
   não deslocar para centroides ou pontos OSM próximos.
9. Exportar e verificar o pacote público. Falha em qualquer etapa retorna código
   diferente de zero e relatório, sem substituir uma publicação anterior.

## Limites do significado

São registros escolares declarados ativos e públicos (dependência 1/2/3,
situação 1) na tabela selecionada. Não representam vagas, inscrições abertas,
horários atuais, qualidade de ensino ou confirmação presencial. Valores em
branco não se tornam 'não'. Ano de referência e coleta não são intercambiáveis.
A falta de NU_ANO_CENSO na tabela é contada explicitamente; nesse caso o ano vem
da distribuição selecionada, não de uma afirmação que o campo exista.

## Como reproduzir

```sh
python -m pip install -e '.[test]'
python -m pytest backend/tests/test_education_bulk.py -q
python ops/education_bulk.py --year 2025 --output test-results/education-run-1
# Para reutilizar território anteriormente coletado, sem alterar a proveniência:
python ops/education_bulk.py --year 2025 --output test-results/education-run-2 \
  --territory-snapshot /dados/territorio-verificado.db
```

A pasta de saída precisa estar vazia. A workflow `National education intake`
executa a ingestão real e guarda evidências por sete dias. Seu snapshot territorial
padrão é um artefato temporário explicitamente identificado, não dependência
permanente de produção. Não adicionar credenciais nem PDFs pessoais ao repositório.

## Evidência desta alteração

Os testes locais usam dados sintéticos identificados no código para testar
limites, Unicode, classificação, rollback e conservação de proveniência. Não
são corpus nacional e nunca são carregados na inicialização da aplicação.
Resultados do download/importação oficial devem ser lidos no artefato da workflow,
separadamente da aprovação da suíte de software. O processo começa com
`national_catalog_certified=false` e não altera essa declaração por contar UFs.
