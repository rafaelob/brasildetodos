<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Prontidão: o que falta para 100%

**100% não é um teste único nem um percentual que se possa declarar sem dados
oficiais e operação real.** É a soma de quatro resultados independentes:
software aceito, dados nacionais reconciliados, operação pública durável e
sustentabilidade comunitária. Hoje o projeto tem um núcleo local forte; os
outros três ainda têm gates abertos.

## Definição de pronto

| Resultado | O que significa | Estado |
|---|---|---|
| Software | percursos cidadãos e de revisão funcionam, com testes locais e builds | **Forte localmente**; falta leitor de tela e dispositivos físicos; axe A/AA e skip link cobertos no Chromium |
| Dados | ingestão oficial atual, denominadores reconciliados e cobertura nacional explícita | **Parcial**: releases certificadas existem, mas não são um catálogo nacional vivo |
| Operação | domínio/HTTPS, PostgreSQL durável, PITR, backup offsite, restauração ensaiada, monitoramento e rollback | **Fora do escopo desta fase** por decisão do owner; stack local, backup/restore e locks validados |
| Comunidade | licença, conduta, contribuição, triagem, moderação, segurança e cadência de releases | **Em formação** |

## O que já está entregue e verificado

- API FastAPI, React/TypeScript, pt-BR/en/es, mapa progressivo e lista
  independente de WebGL/GPS/tiles.
- Consulta, fichas, favoritos, comparação, regiões, cobertura, observações
  guiadas, grupos privados, documentos e recursos.
- Extração PDF nativa, OCR seletivo, fila privada, sinais de privacidade,
  originais content-addressed e prévia de página com Poppler.
- Coletor privado de documentos PNCP, revisões e `not_listed`.
- Alembic `0002_transferegov_parcerias` com 42 tabelas de runtime; `bdt.migrate`
  com `upgrade`, `stamp`,
  `current` e `check`.
- Compose PostgreSQL local durável em `docker-compose.postgres.yml`, com
  migração one-shot, backup lógico e health em `:8009`.
- Suíte local: **2.201 testes Python aprovados, 17 ignorados**; web **243
  aprovados**; build Vite 8.2.4.
- Releases históricas `public-data-20260906-v1` e
  `education-2025-20260907-v1` instaladas juntas em `data/national.db`:
  **234.209 lugares**, 6.679 recursos, 5.571 municípios, 27 UFs e aceite de API
  em 54 partições. Evidência em
  [`reports/20261021-national-data.json`](../reports/20261021-national-data.json).
- Coletas frescas de 21/10/2026: CNES com **96.607 elegíveis** (1 quarentena
  por nome curto) e Inep 2025 com **138.086 escolas**; verificadas
  separadamente, ainda não fundidas em uma edição nacional certificada.
- Consumidores reviewer-only de empenhos especiais, PDDE e documentos PNCP,
  com paginação, linhas publicadas exatas e `aggregate: null`; amostras reais
  de 200 empenhos bounded e um documento de 87.356 bytes, sem bytes públicos.
- Conector bounded de Parcerias do Transferegov com 200 linhas de 89.695
  declaradas e consumidor reviewer-only do cabeçalho exato; sem somas ou
  vínculo territorial.
- Pins de segurança `certifi==2026.10.19` e `Pillow==13.0.0` no lock e no
  worker documental, corrigindo GHSA-6q48/GHSA-8g5g.
- Locks Windows CPython 3.14.8/AMD64 (54 pacotes), macOS arm64 (50) e Linux
  (51), com manifestos e suítes integrais validadas; macOS Intel e outras
  arquiteturas ainda não estão cobertos.
- Auditoria axe-core 4.10.3 (WCAG A/AA) sem violações em exploração, ficha e
  colaboração a 320/390/1440 px; skip link com foco real em `#main` e
  landmarks `main`/`banner`/`navigation`/`h1` verificados. Auditoria humana foi
  retirada do escopo por decisão do owner.
- Fotos aprovadas de observações compartilhadas podem ser vistas apenas por
  membros do grupo, com rota privada e sem publicação automática.
- Backup lógico local e restore em banco novo validados
  (`0002_transferegov_parcerias`, 43 tabelas incluindo `alembic_version`); não
  é PITR nem backup offsite de produção.

Evidências: [Status](STATUS.md), [Matriz de capacidades](FEATURE_MATRIX.md),
[Operação](OPERATIONS.md), [Migrações](MIGRATIONS.md) e
[changes/](changes/).

## Gates pendentes

### 1. Dados nacionais

- Atualizar IBGE, Inep, CNES, PNCP, Transferegov e Obrasgov com competência e
  data de referência explícitas.
- Reconciliar denominadores oficiais e explicar leituras, exclusões e
  quarentena; presença em 27 UFs não é completude.
- Produzir uma edição nacional revisada, com hashes, retomada, idempotência e
  política de revisita.
- Não transformar release histórica em “catálogo vivo” nem preencher lacunas
  com dados sintéticos.

**Aceite:** uma edição oficial reproduzível, reconciliada por território e
fonte, instalada em banco novo, com `national_catalog_certified` decidido por
evidência — não por um botão.

### 2. Documentos, OCR e privacidade

- Corpus oficial anotado, com métricas por campo, abstenção e revisão humana.
- Avaliar assinaturas, anexos e dados pessoais em corpus real; definir
  retenção, expurgo e resposta a incidentes.
- Validar a prévia de página com Poppler em corpus oficial, não só sintético.
- Definir política de exposição de excertos e de documentos originais.

**Aceite:** qualidade medida em corpus oficial, com limites publicados e
revisão jurídica/operacional aplicável.

### 3. Produção

**Fora do escopo desta fase** por decisão do owner em 21/10/2026: não haverá
domínio/HTTPS, PITR, backup offsite, monitoramento ou deploy público. O stack
local, o backup/restore e os locks continuam documentados; um alvo futuro exige
nova ordem e o checklist de produção original.

### 4. Comunidade e operação

- Triagem de issues, revisão de PRs, cadência de releases e mantenedores
  identificados.
- Política de moderação, conduta, conflito de interesse e apelação.
- Canal privado de segurança e processo de divulgação responsável.
- Licenças de dados/mapas/fotos revisadas e créditos mantidos.
- Boas primeiras tarefas e documentação para novos contribuidores.

**Aceite:** alguém de fora consegue abrir uma issue, entender o escopo,
executar os testes locais e receber uma revisão sem depender do autor original.

### 5. Produto ainda não entregue

- Panoramas opcionais com licença/data e provedor definidos.
- macOS Intel e outras arquiteturas; Linux, Windows AMD64 e macOS arm64 já têm
  locks e suítes validadas.
- Tiles vetoriais nacionais/3D com fonte licenciada; o mapa atual é
  progressivo e opcional.

## O que não vamos fazer para “fechar” 100%

- Inventar coordenadas, vínculos, valores, datas ou cobertura.
- Publicar extração de PDF ou foto automaticamente.
- Tratar Docker Compose local como produção.
- Declarar `national_catalog_certified` verdadeiro sem denominadores e
  reconciliação.
- Baixar um gate de segurança, acessibilidade ou teste para acomodar uma falha.

## Como ajudar

Comece por [CONTRIBUTING.md](../CONTRIBUTING.md). Tarefas boas para a primeira
contribuição: revisão de documentação em inglês/espanhol, testes de restore
PostgreSQL local, auditoria de acessibilidade, revisão de licença de uma fonte
oficial e lock macOS Intel. Abra uma issue com o contexto antes de um
patch grande; dados pessoais e segredos nunca entram em issue pública.
