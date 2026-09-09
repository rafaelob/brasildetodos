# Brasil de Todos

**O mapa vivo do que é público.** Plataforma web open source para encontrar serviços, acompanhar intervenções e contribuir com informações revisadas sobre o território brasileiro. Educação e saúde, mapas 2D/3D, documentos e recursos públicos. O runtime não exige LLM, banco vetorial nem chave paga de mapa.

> **Este clone começa vazio.** Escopo nacional é requisito do produto, não cobertura desta instalação. Não há dados demonstrativos disfarçados de registros oficiais. Edições certificadas existem como releases distintas no GitHub (`public-data-20260906-v1`, `education-2025-20260907-v1`) e **não** são os totais desta cópia. Instalá-las é passo de operador, separado do `git clone`. `GET /api/coverage` é a verdade desta instalação; `national_catalog_certified` é sempre `false`.

## Fontes

Seis famílias. O mapa canônico (conector × esta instalação × última edição certificada) está em [Fontes](docs/SOURCES.md). Comandos de importação, perfis e falhas explícitas: [Dados](docs/DATA.md). Contagens abaixo descrevem artefatos publicados, não o banco deste clone.

- **IBGE** — municípios (tabela territorial; conversão de códigos depende desta carga).
- **Inep** — Censo Escolar. Edição certificada `education-2025-20260907-v1`: 138.086 escolas públicas ativas declaradas, 0 geometria. Continuam na lista; não são vagas.
- **CNES** — estabelecimentos. Edição certificada `public-data-20260906-v1`: 96.123 no perfil ambulatorial SUS declarado. Não é toda a rede SUS nem agenda em tempo real. A primeira página da API não é o Brasil.
- **PNCP** — contratos (metadados da consulta, não pagamentos). Município do comprador não é local de execução.
- **Transferegov** — transferências via CSV e perfil revisado. Relatório ou cache com `records_imported: 0` é congelamento de inspeção, não sucesso silencioso. Fases financeiras não se somam.
- **Obrasgov** — projetos. Não gera pin pelo endereço do comprador nem por proximidade de nome.

A verdade ao vivo desta instalação é `GET /api/coverage` (`national_catalog_certified` permanece `false` mesmo depois de importar um arquivo nacional ou uma edição certificada). Importadores aceitam arquivos oficiais; ingestão integral, volumes e completude por território só existem quando certificados à parte.

## Implementado

- API FastAPI com pesquisa, filtros, paginação, consulta espacial, fichas, proveniência, histórico e cobertura observada.
- React/TypeScript com português, inglês e espanhol; mapa MapLibre/OpenFreeMap sob ativação explícita, agrupamentos e extrusão de prédios com alturas presentes na camada. Lista funciona sem mapa.
- Favoritos locais; cadastro opcional, sessões, submissão de observações, fila de revisão e publicação somente após decisão independente. Uma contribuição aprovada é compartilhada; uma pendente não é pública.
- Importação IBGE JSON, CNES JSON/CSV no perfil inspecionado, Inep CSV/ZIP no perfil validado, lugares normalizados e eventos financeiros. Mapeamento explícito de colunas Transferegov e normalizador de metadados PNCP.
- Arquivos originais com hash, falha atômica por arquivo, registros sem coordenadas preservados, retirada de busca diante de ineligibilidade explícita e histórico sem novidades artificiais por mudança de data de coleta.
- Extração PDF nativa com palavras/coordenadas, tabelas e candidatos de convênios/propostas/valores; OCR Tesseract de página selecionada como opção local. Nenhuma interpretação extraída se publica automaticamente.
- Valores financeiros por fase/escopo/fonte. Empenho, transferência, contrato e pagamento nunca são somados como investimentos independentes.

## Iniciar localmente

Requer **Python 3.14.7** e **Node.js 24.20.0**, fixados em `.python-version`,
`.nvmrc` e `.node-version`. CI, containers e desenvolvimento usam esses mesmos
runtimes; não há fallback silencioso para outra versão.

Validação: `python ops/check_toolchain.py --runtime python` e
`node ops/check-node.mjs`. Veja `docs/TOOLCHAIN.md`.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
bdt init-db
cd web
npm install
npm run build
cd ..
uvicorn bdt.api:create_app --factory --host 127.0.0.1 --port 8000
```

Abra `http://localhost:8000`. Para desenvolvimento, rode a API na porta 8000 e `npm run dev` em `web/` (proxy `/api`). Use `BDT_PUBLIC_ORIGIN=http://localhost:5173` na API quando o navegador usar essa origem. Depois do init, `GET /api/coverage` deve mostrar catálogo vazio e `national_catalog_certified: false`.

### Dados reais, não seeds

```bash
bdt download https://servicodados.ibge.gov.br/api/v1/localidades/municipios data/municipios.json
bdt import-ibge data/municipios.json \
  --url https://servicodados.ibge.gov.br/api/v1/localidades/municipios \
  --reference-date DATA_DA_EDICAO
```

Substitua `DATA_DA_EDICAO` pela referência efetiva. Para as demais famílias, siga [Fontes](docs/SOURCES.md) e [o guia de dados](docs/DATA.md). **Não use a primeira página da API CNES como se fosse o Brasil inteiro.** Download não equivale a cobertura certificada. Edições GitHub não entram sozinhas neste banco.

### Colaboração

```bash
bdt create-user revisor --role reviewer
bdt create-user participante
```

As senhas são solicitadas interativamente. Não há usuário nem senha padrão. Cadastro público é desligado por padrão; use `BDT_ALLOW_REGISTRATION=1` somente com responsáveis pela moderação e política de operação. O revisor não pode aprovar a própria contribuição. Fotos, imagens de pacientes/alunos e localização pessoal não são recebidas nesta versão.

### Documentos

```bash
bdt extract-pdf /caminho/arquivo.pdf --output data/extracao.json
# Apenas depois de inspecionar a página e constatar que texto nativo não resolve:
bdt extract-pdf /caminho/arquivo.pdf --output data/extracao.json --ocr-page 2 --language por
```

OCR exige Poppler e Tesseract/idioma português em worker isolado. O original nunca é reescrito. PDF pode conter informações pessoais: resultado de extração fica no ambiente do operador, não num endpoint público. Veja [processamento e limites](docs/ARCHITECTURE.md).

## Testes

```bash
python -m pytest --cov=bdt --cov-report=term-missing
cd web && npm test && npm run build
```

Testes usam dados sintéticos exclusivamente em `backend/tests/`; não comprovam cadastro nacional ou atualidade das fontes. CI compila frontend e executa os testes. Veja [evidências e pendências](docs/STATUS.md).

## Implantação

```bash
docker compose up --build
```

Isso abre uma instância **local**, vazia, com volume SQLite. Por omissão o Compose publica `127.0.0.1:8008` (`BDT_PORT`); loopback e porta 8008 **não** são produção. A imagem roda sem root e serve interface e API na mesma origem. Produção exige HTTPS, domínio permitido, revisão de segurança, backup e responsáveis — este repositório não certifica esse passo. PostgreSQL é suportado pelo acesso relacional; PostGIS/tiles vetoriais/migrações evolutivas e implantação cloud são próximos incrementos, não funcionalidades já certificadas. [Operação](docs/OPERATIONS.md).

## Limites conhecidos

- Clone vazio não é catálogo nacional. Edições certificadas no GitHub não alteram `national_catalog_certified`. Não há sincronização automática de todos os portais, correlação completa entre instrumentos nem deploy público nesta entrega.
- O importador Inep exige os cabeçalhos declarados. Uma nova edição com formato diferente deve receber perfil revisado; falha explícita é preferível a adivinhar campos.
- CNES: o recorte atual é atendimento **ambulatorial SUS declarado**, não toda rede SUS, não prova de propriedade pública e não agenda em tempo real.
- Obras entram como registros normalizados com referência; PNCP/Transferegov/Obrasgov não geram pinos por endereço do comprador ou proximidade de nome.
- O mapa consulta o recorte visível independentemente da página da lista, agrupando pontos quando necessário. Isso não certifica a completude do catálogo ou a renderização externa. 3D depende de altura publicada e zoom; não é gêmeo digital, análise de acessibilidade ou fotografia atual.
- Não há Mapillary/Panoramax, grupos síncronos, envio automático a órgãos públicos ou autenticação gov.br.
- Código não interpreta conformidade legal, não detecta corrupção e não substitui profissionais ou autoridades. Informação oficial, observação e hipótese permanecem distintas.

## Documentação e colaboração

[Fontes](docs/SOURCES.md) · [Dados](docs/DATA.md) · [Arquitetura](docs/ARCHITECTURE.md) · [Operação](docs/OPERATIONS.md) · [Roadmap](docs/ROADMAP.md) · [Segurança](SECURITY.md) · [Contribuir](CONTRIBUTING.md).

## Licenciamento

Código original: **AGPL-3.0-or-later**; texto integral em `LICENSE`. Documentação original em `docs/`: **CC-BY-4.0**, salvo indicação específica. Dados, mapas, bibliotecas e documentos de terceiros conservam suas licenças. Consulte [atribuição](docs/ATTRIBUTION.md). A licença de código não autoriza apresentar um fork como a instância oficial. Projeto independente, sem afiliação presumida a órgão público.
