<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Operação

## O que não é produção

`compose.yaml` é a fonte do runtime local; `docker-compose.yml` apenas a inclui para compatibilidade. O serviço `app` publica só `127.0.0.1:${BDT_PORT:-8008}` → porta 8000 no container. `BDT_ENV=development`, `BDT_DATABASE_URL=sqlite:////app/data/bdt.db`, volume `bdt-data`. Loopback `:8008` e esse SQLite são instância **local**. A imagem cria `/app/data` vazio; `create_all` monta o esquema sem registros oficiais nem bootstrap sintético. Dados que o operador gravar no volume continuam locais — persistência não é catálogo nacional. Não alargar o bind do anfitrião para `0.0.0.0`.

Compose, localhost, SQLite vazio ou local, `TEST_READY.md` e os 214 testes E2E **não** são aceite nacional nem certificação de produção. Publicação, testes verdes, ingestão nacional e deploy público são resultados distintos; este repositório não executa o último.

Produção exige autorização explícita do responsável pelo serviço: domínio próprio, HTTPS (`BDT_ENV=production` recusa `BDT_PUBLIC_ORIGIN` sem `https://` e aplica cookie Secure + HSTS), PostgreSQL durável (extra `.[postgres]`; o Compose não usa Postgres), ensaio de backup e restauração, moderadores independentes do autor e política de retenção. Variáveis: seção seguinte. Backup: [Recuperação](RECOVERY.md). Sem essa ordem, não há implantação pública.

## Instalação e responsabilidades

Ler README. `.env.example` é referência; CLI/uvicorn leem variáveis do processo, não carregam `.env` automaticamente. Não existem recursos cloud criados por este commit.

Para um serviço público autorizado: BDT_ENV=production; BDT_PUBLIC_ORIGIN=https://DOMINIO; BDT_ALLOWED_HOSTS=DOMINIO,127.0.0.1; BDT_REVISION=SHA completo do commit implantado. BDT_ALLOW_REGISTRATION=0 até operação responsável. Mesma origem para web/API. Não servir sem TLS com cookies de produção.

Use PostgreSQL e instalação `.[postgres]` para replicação/concorrência; BDT_DATABASE_URL=postgresql+psycopg://... via gerenciador de segredos. A conexão não deve ser impressa nos logs. O perfil Compose `test` prova o esquema e a jornada de moderação em um PostgreSQL efêmero; ele não cobre durabilidade, PostGIS, migrações de versões anteriores nem múltiplas réplicas, que continuam como gates posteriores.

## Prova PostgreSQL local

```bash
mkdir -p test-results/runtime
docker compose --profile test run --rm --build postgres-proof
docker compose --profile test rm --stop --force postgres-test
```

O banco do perfil fica em `tmpfs`, não publica porta, conecta a aplicação com papel sem privilégios
administrativos e usa somente dados sintéticos. A prova exige
schema vazio, executa a inicialização duas vezes, inspeciona chaves estrangeiras, unicidade e índice,
confirma rollback após violação de constraint e percorre contribuição → moderação → leitura pública.
O recibo fica em `test-results/runtime/postgres.json`. Indisponibilidade do serviço falha a prova;
não existe fallback para SQLite. Consulte o [registro de configuração](configuration.md).

## Processamento

Importar IBGE primeiro, depois cadastros, depois registros vinculados. Executar em worker; não em requisição HTTP. Limitar download e fan-out; monitorar código de saída, manifesto, counts/status. A coleta conserva arquivo + .manifest.json. Não remover a versão anterior antes de aprovar a nova. A versão atual garante atomicidade por arquivo, não por um país inteiro distribuído entre múltiplos arquivos.

## Documentos isolados

```bash
docker build -f ops/Dockerfile.documents -t bdt-documents .
# Ajuste permissões de input/output para o UID 10001; pastas devem existir.
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
  --memory 1g --cpus 1 --pids-limit 64 --tmpfs /tmp:rw,noexec,nosuid,size=256m \
  -v "$PWD/input:/input:ro" -v "$PWD/output:/output" bdt-documents \
  /input/arquivo.pdf --output /output/extraido.json
```

OCR selecionado adiciona `--ocr-page N --language por`. O pipeline não foi avaliado em corpus oficial digitalizado neste ambiente. Faça benchmark de tempo, qualidade por campo e revisão humana antes de dimensionar lotes.

### Originais de evidência

Depois de registrar o documento, o operador armazena o PDF original em pasta privada
content-addressed. O hash precisa ser idêntico ao `snapshot_sha256` da fonte:

```bash
python -m bdt.document_originals store \
  --database sqlite:///data/bdt.db \
  --folder data/document-originals \
  --document-id <id-de-64-hex> \
  --path /caminho/arquivo.pdf \
  --operator <revisor-existente>
```

O comando não publica, não extrai texto e não cria vínculo. O download em
`/api/workbench/documents/{id}/original` exige revisor autenticado, confere o hash
novamente e responde como anexo com `no-store`. A pasta deve ficar fora de
`BDT_STATIC_DIR`; hash não substitui backup.

A prévia de uma página usa o `pdftoppm` local do Poppler. Sem ele, a rota
`/api/workbench/documents/{id}/pages/{page}/image` responde 503 e o Workbench
mantém texto e candidatos; a prévia nunca é publicada.

Antes de limpar ou restaurar, verifique cada referência atual e histórica. O
comando não altera arquivos e separa ausente, corrompido e verificado:

```bash
python -m bdt.private_store_admin verify \
  --database sqlite:///data/bdt.db \
  --folder data/document-originals
```

Órfãos do store podem ser listados sem remoção e, com decisão explícita do
operador, removidos após a janela de retenção. Hashes referenciados pelo
documento atual, por qualquer revisão PNCP ou por um original são preservados:

```bash
# dry-run: não apaga nada
python -m bdt.private_store_admin prune \
  --database sqlite:///data/bdt.db \
  --folder data/document-originals \
  --older-than-days 30

# somente após revisar o relatório
python -m bdt.private_store_admin prune ... --apply
```

O comando não substitui backup nem expurgo legal de documento referenciado.

## Recuperação

Backup do banco e do armazenamento de originais são operações distintas. SQLite ativo requer backup consistente via sqlite backup API, não cópia isolada do arquivo ignorando WAL. PostgreSQL exige backup/restauração testados. Nunca tratar hash como cópia de segurança. Testar upgrade de schema em clone antes de produção.

## Observabilidade e restrições

/api/health verifica banco; /api/coverage relata dados realmente carregados; /api/config aponta para código da versão se BDT_REVISION for SHA válido. Registrar métricas, não texto de observações/senhas/PDFs. Trinta runs e cem observações são limites de visualização, não histórico apagado.

Fila/moderação requer pessoa independente do autor. Recuperação de senha usa código de uso único gerado pelo titular autenticado; não há e-mail nem gov.br. `GET /api/config` `photo_uploads` permanece falso salvo `BDT_PHOTO_UPLOADS=1` (não ligar em Compose). Contestação de observação rejeitada pede re-revisão a outra pessoa; não publica sozinha. Providenciar canal de suporte/retirada e política de retenção antes de convite público amplo. Rate limit por peer depende da topologia de proxy; não habilitar confiança irrestrita em forwarded headers.
