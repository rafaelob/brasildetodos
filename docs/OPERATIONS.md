<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Operação

## Instalação e responsabilidades

Ler README. `.env.example` é referência; CLI/uvicorn leem variáveis do processo, não carregam `.env` automaticamente. Docker Compose inicial é local e SQLite persistente; não é infraestrutura cloud completa. Não existem recursos cloud criados por este commit.

Para produção: BDT_ENV=production; BDT_PUBLIC_ORIGIN=https://DOMINIO; BDT_ALLOWED_HOSTS=DOMINIO,127.0.0.1; BDT_REVISION=SHA completo do commit implantado. BDT_ALLOW_REGISTRATION=0 até operação responsável. Mesma origem para web/API. Não servir sem TLS com cookies de produção.

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

Fila/moderação requer pessoa independente do autor. Não há reset de senha por email nem exclusão de conta self-service nesta entrega. Providenciar canal de suporte/retirada e política de retenção antes de convite público amplo. Rate limit por peer depende da topologia de proxy; não habilitar confiança irrestrita em forwarded headers.
