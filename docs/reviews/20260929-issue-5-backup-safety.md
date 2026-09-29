# Backup: revogação de recuperação e integridade do snapshot

Refs #5. Base: `f95c43955d95b2bf800535729f9b5f8099f4bd5b`.

Um código de recuperação consumido depois da criação do backup podia reaparecer na restauração. `recovery_codes` passa a ser limpo na transação que revoga sessões e convites, sem impedir backups anteriores à criação dessa tabela. Falhas na revogação não instalam o destino.

O manifesto cobre o arquivo principal, não journals externos. Snapshots rejeitam auxiliares `-wal`, `-shm`, `-journal`, incluindo symlinks pendentes, e usam `immutable=1`. A origem viva continua usando a API de backup online com visibilidade do WAL legítimo, para não perder commits não checkpointados.

## Testes suplementares

13 casos novos: códigos consumidos, esquema antigo, auxiliares/symlinks, WAL real sobreposto sem mudar o hash principal, arquivos surgidos após validação/durante cópia, isolamento da conexão e revogação abortada. Fatia isolada: 96 aprovados (13 novos + 83 existentes). Quatro fatias combinadas reexecutadas: 230 aprovados.

Python 3.13.5/pytest 9.0.2 auxiliares; não substituem suíte integral em Python 3.14.7. Sem banco real, PostgreSQL, frontend ou deploy. Estado remoto da CI deve ser verificado no PR. Complementa o PR #9, que trata da atomicidade de inicialização do esquema.

```sh
python -m pytest backend/tests/test_backup_credential_snapshot.py backend/tests/test_domain.py backend/tests/test_documents.py backend/tests/test_backup.py -q
```

## Limites operacionais

`immutable=1` pressupõe arquivo principal realmente estável. Não é defesa completa contra adversário que controla o diretório/arquivo principal e alterna/reverte seus bytes durante a leitura. Backup permanece privado e não criptografado. Senhas restauradas, exclusões posteriores, papéis e política de recuperação ainda exigem reconciliação do operador. Nenhum backup privado é anexado ao PR.

Referências primárias: https://www.sqlite.org/uri.html e https://www.sqlite.org/backup.html .
