<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Dados nacionais reais instalados e fontes atualizadas

Lote de 21/10/2026. Base de integração no `main`: `1ce87f2`.

## O que foi obtido

- Releases verificadas `public-data-20260906-v1` (28.096.042 bytes,
  SHA-256 `6d62f9ca…cc1639`) e `education-2025-20260907-v1` (23.807.757 bytes,
  SHA-256 `483bba3a…5fcfe7`) baixadas dos GitHub Releases e instaladas juntas
  em `data/national.db`.
- Resultado da instalação: **234.209 lugares** (96.123 saúde + 138.086 escolas),
  **6.679 recursos**, **5.571 municípios**, **27 UFs**, 138.093 lugares sem
  geometria e zero contas/observações. O aceite de API passou em 54 partições
  e as rotas privadas continuaram em 401.
- Coleta fresca CNES em 21/10/2026: 56.656.725 bytes, SHA-256 `481f5200…f4ef8`,
  640.494 linhas, **96.607 elegíveis**, 543.886 excluídas pelo perfil, **1 em
  quarentena** por nome curto e 6 sem geometria. Catálogo público exportado e
  reinstalado em banco novo com sucesso.
- Coleta fresca Inep 2025: 537.217.189 bytes, SHA-256 `ad2c3891…fc90a`,
  214.192 linhas, **138.086 elegíveis**, 76.106 excluídas e 0 com geometria.
  A tabela revisada tem 27 UFs e o aceite de catálogo/API passou.
- Instância local em `http://127.0.0.1:8009` com o banco nacional, frontend
  compilado e `/api/health` saudável. É um SQLite local, **não produção**.

## Evidência

O recibo agregado, sem dados pessoais e sem linhas completas, está em
[`reports/20261021-national-data.json`](../../reports/20261021-national-data.json).
Os pacotes baixados, o banco e os catálogos temporários ficam em `data/` e
`test-results/` (ignorados pelo Git); não são publicados como release.

Reprodução:

```bash
gh release download public-data-20260906-v1 --pattern public-data.zip --dir data/downloads/releases
gh release download education-2025-20260907-v1 --pattern education-catalog.zip --dir data/downloads/releases
python ops/install_national_catalog.py \
  --health data/downloads/releases/public-data.zip \
  --education data/downloads/releases/education-catalog.zip \
  --output data/national.db
python ops/national_catalog_acceptance.py \
  --health data/downloads/releases/public-data.zip \
  --education data/downloads/releases/education-catalog.zip \
  --output test-results/national-acceptance
```

## Limites

`national_catalog_certified` continua **false**. A instalação combina releases
históricas; as coletas frescas de CNES/Inep foram verificadas separadamente e
não foram fundidas no banco instalado. Não há reconciliação de denominadores
municipais/estaduais/nacionais, benchmark PostgreSQL desta carga, publicação
pública, PITR, backup offsite ou restauração de produção. A Issue #2 permanece
aberta; a Issue #5 continua separada para operação pública.
