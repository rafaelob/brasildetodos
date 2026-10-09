<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Inicialização de esquema atômica — Issue #5

`Database.initialize()` não cria mais tabelas antes de conferir versões e
planejar as colunas ausentes. Versão incompatível ou alteração não suportada
falha antes de qualquer DDL. Os identificadores e defaults são compilados pelo
dialeto SQLAlchemy; strings como `O'Reilly` não viram SQL sem aspas.

Inspeção, `create_all`, alterações aditivas e registro das versões dos módulos
carregados usam uma única conexão/transação. SQLite inicia `BEGIN IMMEDIATE`
explicitamente, pois o modo legado de sqlite3 não inicia transação em DDL;
PostgreSQL usa o advisory lock transacional de duas chaves `(4342868, 1)` para
serializar inicializadores do Brasil de Todos no mesmo banco. Versões conhecidas
já persistidas são verificadas mesmo antes da importação do módulo opcional.

Referências técnicas: [PostgreSQL — advisory locks transacionais](https://www.postgresql.org/docs/current/functions-admin.html#FUNCTIONS-ADVISORY-LOCKS) e [SQLAlchemy — transações do SQLite](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#legacy-transaction-mode-with-the-sqlite3-driver).

Testes SQLite: recusa de quatro famílias de versão futura, formato incompatível,
falha no segundo ALTER seguida de rollback/retry, preservação de linhas,
identificadores/defaults com aspas e oito inicializações em quatro threads.
`python -m pytest backend/tests/test_schema_upgrade.py backend/tests/test_schema_atomicity.py`.

A prova PostgreSQL do perfil Compose isolado agora exercita rollback de DDL,
quatro inicializadores concorrentes, default textual e uma FK efetivamente
rejeitando referência inexistente. Seu recibo continua em
`test-results/runtime/postgres.json`. A CI Runtime integration passa a rodar em
PRs dos arquivos de esquema/runtime, com concorrência separada por ref e sem
permissão adicional. Não há fallback para SQLite quando PostgreSQL falha.

Isto protege a inicialização aditiva existente, **não implementa Alembic**, não
valida automaticamente tipos/constraints preexistentes nem migrações destrutivas,
e não certifica recuperação de produção. Chaves, índices, colunas geradas e
opções de FK que não possam ser acrescentadas com segurança exigem migração
revisada. Inicializadores opcionais chamados separadamente não formam uma única
transação global com toda a inicialização da aplicação. Backup/restauração,
segurança, acessibilidade assistiva e deploy público continuam gates da #5.
