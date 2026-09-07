<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Censo Escolar 2025 — catálogo público verificável

Esta distribuição preserva, sem alterar seus bytes, o artefato público da coleta
`34078768110`, revisão `96aa4bf80cc13402f0d35d47a8deabcae6d30db3`.
Não é um novo download do Inep nem uma instância da aplicação em produção.

## Conteúdo e alcance

São 138.086 escolas públicas declaradas ativas, selecionadas entre 214.192 linhas
escolares; 76.106 linhas ficaram fora do perfil. O catálogo inclui registros das
27 UFs e 5.571 registros territoriais IBGE reutilizados com proveniência.
Todos os registros escolares estão sem coordenadas nesta fonte: continuam na
busca/lista, sem pontos geocodificados por aproximação. Não são vagas escolares.

O ZIP contém somente cinco tabelas normalizadas públicas, manifesto do catálogo,
relatório da importação e recibo do download original. Não contém registros
individuais de alunos/docentes, contas, sessões, observações, originais de cidadãos
ou arquivos temporários. Recursos e eventos financeiros estão vazios. O ZIP bruto
do Inep (537.217.189 bytes) não está incluído: o hash e a referência estão no recibo.
A presença nas 27 UFs não certifica completude além dos filtros e da edição usada.

## Verificação e uso

A seleção independente está em `data/releases/education-2025-20260907-v1.json`.
Hash SHA-256 do arquivo `education-catalog.zip`:
`483bba3a2e71d5360061cbc1880b41c8ab4915e94199a74bb8ac5678ee5fcfe7`.
Tamanho: 23.807.757 bytes. O arquivo é idêntico ao artefato selecionado; a release
não altera nem substitui `public-data-20260906-v1`.

Com Python 3.14.7 e as dependências travadas instaladas:

```sh
python ops/education_release.py education-catalog.zip --selection data/releases/education-2025-20260907-v1.json
```

O comando confere os bytes, extrai uma lista fechada em diretório temporário,
valida todas as linhas/partições, instala um banco novo e consulta a API. Nenhum
banco existente é modificado. Para operar o catálogo, extraia o ZIP já verificado
em uma pasta nova e use o instalador existente:

```sh
python -m bdt.catalog_release install ./public-catalog --output ./data/schools.db
```

Este comando cria outro banco; não o copie por cima do banco da saúde ou de um
banco com usuários. A combinação durável de catálogos exige importação coordenada,
não substituição de arquivos. As datas de coleta e referência ficam preservadas.

O workflow de publicação exige antes o percurso de navegador com frontend
compilado em Node 24.20.0, API e registros reais. Em seguida baixa o próprio asset
publicado e reexecuta a validação. Uma nova seleção exige tag e revisão distintas.
Não há sobrescrita de assets. O hash no código protege contra troca de bytes,
mas não transforma a release em um serviço administrativamente imutável.

## Origem e reutilização

Fonte: Inep/MEC, Censo Escolar da Educação Básica 2025, tabela escolar V2;
território: IBGE. URLs, datas, filtros, perfis e hashes permanecem nos registros.
A licença AGPL do software não substitui as condições dos dados da fonte. Preserve
atribuição e proveniência. O projeto é independente e não representa esses órgãos.
A publicação não confirma contatos, funcionamento presente, acessibilidade,
qualidade de ensino ou atendimento a uma solicitação de matrícula.
