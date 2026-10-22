<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Dependências reproduzíveis

Alvos: Python 3.14.8 e Node.js 24.20.0. Não substituir por latest ou por uma
versão local disponível. Ver `TOOLCHAIN.md`.

## Web

O workflow `dependency-lock.yml` gera `web/package-lock.json`, instala via
`npm ci`, testa, compila e executa `npm audit --audit-level=high` antes de
publicar somente o lock no main. Isso não garante ausência de vulnerabilidade
futura. Uma atualização concorrente do manifesto impede publicar um lock obsoleto.

## Backend Linux

O workflow `python-lock.yml` resolve runtime, testes, PostgreSQL e build com
pip-tools 7.6.1 no CPython 3.14.8/Linux. Cada distribuição tem hashes SHA-256.
Uma venv nova instala com `--require-hashes` e somente wheels; o projeto local
é instalado sem nova resolução nem build isolado que busque outras versões.
A suíte de backend e o piso de cobertura são obrigatórios antes da publicação.
`ops/python_lock_manifest.py` confere pins, hashes do lock e do pyproject,
contagem e versões instaladas. Mudança do manifesto exige regeneração. O lock
Linux atual tem 51 pacotes e inclui os extras de migração (`alembic==1.20.0`)
e MCP, além de `certifi==2026.10.19` e `Pillow==13.0.0`; a regeneração de
21/10/2026 foi verificada com instalação hash-checked.

## Backend Windows

`requirements/windows-py314.lock` é gerado no CPython 3.14.8/AMD64 com
pip-tools 7.6.1, usando o lock Linux como constraint para manter uma única
versão dos 51 pacotes comuns. Ele adiciona apenas `colorama`, `pywin32` e
`tzdata`, totalizando 54 pacotes com hashes SHA-256. O manifesto
`requirements/windows-py314.json` registra plataforma, arquitetura, hashes do
lock e do pyproject e a contagem.

A validação de 21/10/2026 usou venv nova em Windows/AMD64: instalação
`--require-hashes --only-binary=:all:`, projeto editável sem resolução,
`pip check` e a suíte integral **2.192 aprovados, 17 ignorados, zero falhas**.
A instalação também foi repetida com `pip`; o lock não é universal e não foi
executado em CI Windows. A auditoria de vulnerabilidades continua separada.

```powershell
python ops/python_lock_manifest.py verify --lock requirements/windows-py314.lock `
  --manifest requirements/windows-py314.json --system Windows
python -m venv .venv
.\.venv\Scripts\python -m pip install --require-hashes --only-binary=:all: `
  -r requirements\windows-py314.lock
.\.venv\Scripts\python -m pip install --no-deps --no-build-isolation -e .
.\.venv\Scripts\python -m pip check
.\.venv\Scripts\python -m pytest
```

## Backend macOS arm64

`requirements/macos-py314.lock` foi gerado no CPython 3.14.8/arm64 pelo workflow
manual `.github/workflows/macos-lock.yml`, usando o lock Linux como constraint.
São 50 pacotes; os 50 pins comuns são idênticos ao Linux e `greenlet` não é
resolvido neste alvo (o runtime é síncrono). O manifesto
`requirements/macos-py314.json` registra `Darwin`/`arm64`, hashes do lock e do
pyproject e a contagem.

O run público [39696830961](https://github.com/rafaelob/brasildetodos/actions/runs/39696830961)
executou instalação `--require-hashes --only-binary=:all:`, projeto editável,
`pip check`, a suíte integral **2.192 aprovados, 17 ignorados** e a gravação/
verificação do manifesto. O artefato foi baixado e incorporado ao `main`; o
workflow não faz commit automático. macOS Intel e outras arquiteturas não estão
cobertos.

```sh
python ops/python_lock_manifest.py verify --lock requirements/macos-py314.lock \
  --manifest requirements/macos-py314.json --system Darwin
```

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

O lock tem escopo de sistema/versão. macOS Intel e outras arquiteturas ainda
devem receber sua própria validação; não rotular Linux, Windows ou macOS arm64
como universais.
A geração não atualiza automaticamente a instalação de produção. CI/containers
precisam usar a política de instalação travada depois que o lock for confirmado.
O registro de migração informa quais instalações efetivamente o utilizaram.

## Limitações remanescentes

Auditoria de vulnerabilidades Python, digests das imagens, reprodutibilidade do
sistema operacional e navegador, política de renovação e perfis de produção sem
testes. Estes não são encerrados apenas porque o lock foi gerado.

Fontes: https://pip-tools.readthedocs.io/en/stable/ e
https://pypi.org/project/pip-tools/7.6.1/ .
