<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Operação

## O que não é produção

`compose.yaml` / `docker-compose.yml` publicam só `127.0.0.1:${BDT_PORT:-8008}` → porta 8000 no container. `BDT_ENV=development`, `BDT_DATABASE_URL=sqlite:////app/data/bdt.db`, volume `bdt-data`. Loopback `:8008` e esse SQLite são instância **local**. A imagem cria `/app/data` vazio; `create_all` monta o esquema sem registros oficiais nem bootstrap sintético. Dados que o operador gravar no volume continuam locais — persistência não é catálogo nacional. Não alargar o bind do anfitrião para `0.0.0.0`.

Compose, localhost, SQLite vazio ou local, `TEST_READY.md` e os 214 testes E2E **não** são aceite nacional nem certificação de produção. Publicação, testes verdes, ingestão nacional e deploy público são resultados distintos; este repositório não executa o último.

Produção exige autorização explícita do responsável pelo serviço: domínio próprio, HTTPS (`BDT_ENV=production` recusa `BDT_PUBLIC_ORIGIN` sem `https://` e aplica cookie Secure + HSTS), PostgreSQL durável (extra `.[postgres]`; o Compose não usa Postgres), ensaio de backup e restauração, moderadores independentes do autor e política de retenção. Variáveis: seção seguinte. Backup: [Recuperação](RECOVERY.md). Sem essa ordem, não há implantação pública.

## Instalação e responsabilidades

Ler README. `.env.example` é referência; CLI/uvicorn leem variáveis do processo, não carregam `.env` automaticamente. Não existem recursos cloud criados por este commit.

Para um serviço público autorizado: BDT_ENV=production; BDT_PUBLIC_ORIGIN=https://DOMINIO; BDT_ALLOWED_HOSTS=DOMINIO,127.0.0.1; BDT_REVISION=SHA completo do commit implantado. BDT_ALLOW_REGISTRATION=0 até operação responsável. Mesma origem para web/API. Não servir sem TLS com cookies de produção.

Use PostgreSQL e instalação `.[postgres]` para replicação/concorrência; BDT_DATABASE_URL=postgresql+psycopg://... via gerenciador de segredos. A conexão não deve ser impressa nos logs. O suporte relacional é implementado, mas a suíte atual só foi executada em SQLite. PostGIS, migrações e teste multi-replica são gates posteriores.

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

## Recuperação

Backup do banco e do armazenamento de originais são operações distintas. SQLite ativo requer backup consistente via sqlite backup API, não cópia isolada do arquivo ignorando WAL. PostgreSQL exige backup/restauração testados. Nunca tratar hash como cópia de segurança. Testar upgrade de schema em clone antes de produção.

## Observabilidade e restrições

/api/health verifica banco; /api/coverage relata dados realmente carregados; /api/config aponta para código da versão se BDT_REVISION for SHA válido. Registrar métricas, não texto de observações/senhas/PDFs. Trinta runs e cem observações são limites de visualização, não histórico apagado.

Fila/moderação requer pessoa independente do autor. Recuperação de senha usa código de uso único gerado pelo titular autenticado; não há e-mail nem gov.br. `GET /api/config` `photo_uploads` permanece falso salvo `BDT_PHOTO_UPLOADS=1` (não ligar em Compose). Contestação de observação rejeitada pede re-revisão a outra pessoa; não publica sozinha. Providenciar canal de suporte/retirada e política de retenção antes de convite público amplo. Rate limit por peer depende da topologia de proxy; não habilitar confiança irrestrita em forwarded headers.
