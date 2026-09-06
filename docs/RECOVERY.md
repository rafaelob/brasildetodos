<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Recuperação operacional e validação de runtime

## Dois artefatos distintos

Um catálogo público é gerado por `bdt.catalog_release`, com lista explícita de tabelas. Um **backup privado** contém o banco completo, incluindo contas, contribuições privadas e auditoria. Não publique backups em releases, buckets públicos, issues ou artefatos públicos de CI. Os testes de recuperação usam somente bancos sintéticos isolados.

## Backup SQLite consistente

```bash
python -m bdt.backup create data/bdt.db --output /diretorio-privado/backup-20260906
python -m bdt.backup verify /diretorio-privado/backup-20260906
python -m bdt.backup restore /diretorio-privado/backup-20260906 --output data/recovered-new.db
```

A implementação usa a API online de backup SQLite, não uma cópia ingênua do arquivo principal. Isso é importante em modo WAL: alterações confirmadas podem ainda estar no WAL. O destino usa diretório privado e arquivos com modo 0600; o manifesto declara explicitamente `encrypted: false`. Permissões locais não substituem criptografia do volume, controle de acesso, gestão de chaves e transporte autenticado do operador.

A restauração verifica tamanho, hash, esquema, integridade SQLite e chaves estrangeiras. Ela cria um arquivo novo e recusa sobrescrever um destino, inclusive o banco ativo. Revoga as sessões recuperadas e limpa contadores de requisição, exigindo novo login. Os dados de origem e o backup permanecem intactos. Hash e manifesto não são assinatura de autenticidade; mantenha a cadeia de custódia em armazenamento confiável.

A restauração não troca o serviço em execução. Primeiro: isolar o ambiente recuperado, conferir versão do código/esquema, comparar as exclusões e retratações posteriores ao backup, testar e então planejar a troca. **Restaurar um backup antigo pode reintroduzir dados apagados depois dele.** Mantenha o registro restrito de exclusões e os procedimentos de reaplicação separados da cópia restaurada. A política de retenção precisa ser definida pelo operador antes da abertura ampla; não se declara uma conformidade jurídica automática.

O comando limita o tempo da cópia. Bancos de outra aplicação, destinos existentes, symlinks e esquemas desconhecidos são recusados. Este módulo cobre SQLite. Backups PostgreSQL devem usar ferramentas e procedimentos próprios da instalação; não são realizados por este comando.

Referência primária do mecanismo: https://www.sqlite.org/backup.html

## Testes PostgreSQL e container

O workflow `Runtime integration` executa dois trabalhos independentes. Eles produzem relatórios com o SHA testado e **não** implantam uma aplicação pública.

1. PostgreSQL efêmero: esquema vazio, importação sintética, campos JSON/booleanos, busca, viewport, login e rate limiting, observação pendente, revisão por outra pessoa, recusa de revisão duplicada e exportação de catálogo em transação repetível para instalação SQLite. O script recusa hosts não locais, nome de banco diferente de `bdt_ci` e execução sem autorização explícita de teste.
2. Container real: build do Dockerfile da aplicação, frontend compilado, execução sem root, filesystem somente leitura, dados em tmpfs, capacidades removidas e verificação de health, SHA, cabeçalhos, página web e catálogo inicial vazio. Não há bootstrap sintético na imagem normal.

Os resultados de uma execução são evidência daquela revisão, não de revisões posteriores. A saída sintética não deve ser misturada aos dados oficiais. A pipeline normal continua exigindo os testes Python, web e de navegador existentes; o novo workflow não reduz suas exigências.

Comandos locais:

```bash
python -m pytest backend/tests/test_backup.py backend/tests/test_catalog_release.py
# ops/postgres_smoke.py requer PostgreSQL LOCAL efêmero, nome bdt_ci,
# BDT_EPHEMERAL_TEST=1 e BDT_RUNTIME_TEST_DATABASE_URL definidos apenas no ambiente de teste.
```

Antes de operar publicamente continuam necessários: configuração real de HTTPS/origem, armazenamento persistente, credenciais próprias, revisão de dependências, retenção e autorização de publicação dos dados. Teste em container não equivale a deploy; um catálogo válido não equivale a cobertura nacional certificada.
