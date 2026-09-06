<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Dependências reproduzíveis

Alvos: Python 3.14.7 e Node.js 24.20.0. Não substituir por latest ou por uma
versão local disponível. Ver `TOOLCHAIN.md`.

## Web

O workflow `dependency-lock.yml` gera `web/package-lock.json`, instala via
`npm ci`, testa, compila e executa `npm audit --audit-level=high` antes de
publicar somente o lock no main. Isso não garante ausência de vulnerabilidade
futura. Uma atualização concorrente do manifesto impede publicar um lock obsoleto.

## Backend Linux

O workflow `python-lock.yml` resolve runtime, testes, PostgreSQL e build com
pip-tools 7.6.1 no CPython 3.14.7/Linux. Cada distribuição tem hashes SHA-256.
Uma venv nova instala com `--require-hashes` e somente wheels; o projeto local
é instalado sem nova resolução nem build isolado que busque outras versões.
A suíte de backend e o piso de cobertura são obrigatórios antes da publicação.
`ops/python_lock_manifest.py` confere pins, hashes do lock e do pyproject,
contagem e versões instaladas. Mudança do manifesto exige regeneração.

Os artefatos marcados como evidência podem existir mesmo quando o job falha;
não equivalem a lock aprovado. A publicação só acontece após os testes e com
comparação do manifesto no main. Nem o lock nem o relatório certificam dados
nacionais, deploy ou qualidade de OCR em documentos oficiais.

Após publicação de um lock aprovado:

```sh
python ops/python_lock_manifest.py verify
python -m venv .venv
. .venv/bin/activate
python -m pip install --require-hashes --only-binary=:all: -r requirements/linux-py314.lock
python -m pip install --no-deps --no-build-isolation -e .
python -m pip check
python -m pytest
```

O lock tem escopo de sistema/versão. Windows, macOS e outras arquiteturas devem
receber sua própria validação; não rotular o pacote Linux como universal.
A geração não atualiza automaticamente a instalação de produção. CI/containers
precisam usar a política de instalação travada depois que o lock for confirmado.
O registro de migração informa quais instalações efetivamente o utilizaram.

## Limitações remanescentes

Auditoria de vulnerabilidades Python, digests das imagens, reprodutibilidade do
sistema operacional e navegador, política de renovação e perfis de produção sem
testes. Estes não são encerrados apenas porque o lock foi gerado.

Fontes: https://pip-tools.readthedocs.io/en/stable/ e
https://pypi.org/project/pip-tools/7.6.1/ .
