<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Um banco com saúde, escolas e recursos

As duas releases já publicadas são entradas independentes. A instalação conjunta
não cria vínculos entre escolas, unidades e contratos. Não repete a coleta nem
modifica os pacotes originais ou um banco existente. Funciona sem LLM.

## Instalar

Use Python 3.14.7 com `python ops/install_locked.py --editable` e Node 24.20.0
com `npm ci` e `npm run build` na pasta web. Baixe de Releases os dois arquivos:
`public-data-20260906-v1/public-data.zip` e
`education-2025-20260907-v1/education-catalog.zip`.

```sh
python ops/install_national_catalog.py \
  --health ./public-data.zip --education ./education-catalog.zip \
  --output ./data/national.db
BDT_DATABASE_URL=sqlite:///data/national.db \
  uvicorn bdt.api:create_app --factory --host 127.0.0.1 --port 8000
```

O comando deve ser executado a partir da raiz do repositório. O diretório de
saída deve ser privado do operador, sem escritores concorrentes ou ancestrais
alterados por outros usuários. Arquivo, symlink, diretório ou sidecar SQLite no
destino interrompem a instalação. Não copie o resultado por cima de uma base com
usuários. A atualização de uma instalação ativa é outro procedimento, ainda não
implementado por este comando.

## Garantias verificáveis

As seleções em `data/releases/` fixam hashes externos, tamanhos e contagens.
Os arquivos são copiados e verificados antes de ler seus conteúdos. Os municípios
só são compartilhados se cada linha, incluindo a fonte, for idêntica nas duas
entradas; IDs duplicados, ausentes ou divergentes provocam falha. As escolas e
suas versões são inseridas sem substituir identidades existentes. Recursos e
versões contratuais da primeira release permanecem intactos.

A montagem ocorre numa área temporária do mesmo filesystem do destino. Uma falha
descarta essa área. Após conferir totais, partições, chaves estrangeiras,
integridade e checkpoint do WAL, publica-se o arquivo com link atômico sem
sobrescrita. O recibo identifica o hash do banco **antes** de iniciar a aplicação,
que pode criar tabelas próprias. O fsync do arquivo não constitui um ensaio de
recuperação após falta de energia ou garantia universal de todo filesystem.

Para as seleções publicadas, o resultado esperado é 234.209 lugares:
96.123 registros CNES e 138.086 escolas; 6.679 recursos e suas versões;
5.571 municípios compartilhados; 138.093 lugares sem coordenadas.
A presença nas 27 UFs não prova completude de todos os serviços existentes.
O perfil CNES é atendimento ambulatorial SUS declarado, não propriedade pública;
o escolar é rede pública declarada ativa na edição 2025, não disponibilidade de
vagas. Nenhum valor cadastral vira pagamento, e não há total financeiro agregado.

## Aceite independente

```sh
python ops/national_catalog_acceptance.py \
  --health ./public-data.zip --education ./education-catalog.zip \
  --static ./web/dist --output ./test-results/national-acceptance
```

O aceite é dono de uma instalação temporária e a remove ao terminar, inclusive
em falhas. Confere a API por tipo/UF e rotas privadas; com `--static`, usa a
interface realmente compilada e registros dos dois catálogos na mesma sessão.
Exercita filtros, busca, favoritos persistidos, fontes, ausência de geometria e
JSON exportado em pt-BR/en/es e 320/390/1440 pixels. Não simula respostas da API.
Preferências locais do navegador são dados de teste; não são contas de cidadãos.

O workflow `Unified national catalog acceptance` baixa as duas releases existentes
com permissão de leitura e não publica nenhuma aplicação. Somente recibos JSON
e capturas da interface pública são guardados como artefatos; banco, logs locais,
ZIPs de entrada e diretórios temporários não são enviados. Uma execução sem
`--static` jamais declara aprovação de navegador.
