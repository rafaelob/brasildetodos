<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Dados públicos verificados — distribuição v1

Esta distribuição preserva pacotes já coletados e validados pelo projeto; não é
uma nova coleta nem uma aplicação em produção. Contém o catálogo público CNES/IBGE
selecionado e 6.679 recursos: 6.677 contratos PNCP da janela de publicação de
04/09/2026, um plano de transferência especial e um projeto Obrasgov.

## Conteúdo

`public-data.zip` inclui somente as cinco tabelas públicas do catálogo e seu
manifesto, os recursos normalizados e relatório selecionados, o aceite integrado
da API e um manifesto geral. Mantém as fontes, as datas de referência e de coleta,
os hashes e os valores exatos. Não contém contas, sessões, grupos, observações,
textos privados, bancos temporários, quarentena ou microdados individuais.

O catálogo tem 96.123 estabelecimentos elegíveis no perfil declarado de atendimento
ambulatorial SUS, incluindo sete sem coordenadas. A seleção não é uma lista de
vagas/consultas disponíveis nem apenas de prédios de propriedade pública. Não há
catálogo educacional nacional nesta distribuição. Valores de contratos e planos
não representam pagamentos e não devem ser somados entre fases financeiras.
O município do órgão comprador não é atribuído como local da entrega.

## Verificação antes de usar

Baixe `public-data.zip`, `public-data.sha256` e `verification.json` da mesma release.
Com o código deste repositório, Python 3.14.7 e dependências instaladas:

```sh
sha256sum --check public-data.sha256
python ops/public_data_bundle.py verify public-data.zip --sha256 <SHA256_DO_ARQUIVO>
```

A release tem tag `public-data-20260906-v1`. Os arquivos não são sobrescritos por
uma repetição do workflow. A repetição baixa os bytes publicados e verifica tanto
o hash externo quanto as três referências de entrada fixadas no código. Uma
nova edição precisa de outra tag e de uma nova seleção revisada de entradas.

## Instalação

Depois de validar, extraia em uma pasta nova. Instale o catálogo em um banco novo,
nunca por cópia direta sobre um banco ativo com usuários:

```sh
python -m bdt.catalog_release install catalog --output ./data/catalog.db
BDT_DATABASE_URL=sqlite:///./data/catalog.db python -m bdt.resource_release resources \
  --report-sha256 34554d95fe0fa4d0a0211d1c804b9d9c187232ba0f7602b508c7cff8a7b3d3d0 \
  --resources-sha256 d18d05e8a7d98847dad8be3cd774591c35649193be0490f9a0c5ccaa9da76245 \
  --output ./data/resource-install.json
```

Os comandos de instalação são de operador. A aplicação não baixa pacotes nem
processa documentos durante a abertura de uma ficha. A instalação dos recursos
verifica os hashes, usa uma transação e é idempotente; a evidência de instalação
precisa de um caminho de saída novo a cada execução.

## Origem e condições de reutilização

Saúde/território: artefato 9981549978 da execução 34007758949.
Recursos: artefato 9993985086 da execução 34048819034.
Os identificadores e URLs dos registros originais permanecem nos próprios dados.
A licença AGPL do código não substitui as condições das fontes. Preserve autoria,
referências e atribuição de IBGE, Ministério da Saúde/CNES, PNCP, Transferegov e
Obrasgov. Este projeto é independente e não representa esses órgãos.

## O que a validação prova

O construtor congela os bytes selecionados, confere as tabelas, instala em SQLite
temporário, reimporta sem duplicação e consulta a API real. A criação do ZIP usa
uma lista fechada de nomes. A releitura recusa arquivos adicionais, duplicatas,
travessia de diretório, links simbólicos, hashes divergentes e limites excedidos.
Nenhuma origem privada ou diretório arbitrário é exportado.

Consistência de bytes não é certificação de completude nacional, veracidade de
cada registro ou situação atual de funcionamento. A distribuição permite reproduzir
os resultados que efetivamente foram verificados e não elimina essas limitações.
