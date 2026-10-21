<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Lock Windows validado

Lote de 21/10/2026. Base de integração no `main`: `4b22a16`. Código e artefatos
em `ed1a770929866aabdfe8536ad709438a079e5eb2`.

## O que mudou

- `requirements/windows-py314.lock` foi gerado no CPython 3.14.8/AMD64 com
  pip-tools 7.6.1, usando `requirements/linux-py314.lock` como constraint. Os
  51 pacotes comuns ficam na mesma versão do Linux; o Windows adiciona apenas
  `colorama`, `pywin32` e `tzdata`, totalizando 54 pacotes com hashes SHA-256.
- `requirements/windows-py314.json` registra sistema, arquitetura, hashes do
  lock e do pyproject, contagem e o fato de a instalação ter sido verificada.
- `ops/python_lock_manifest.py` passou a aceitar `--lock`, `--manifest`,
  `--system` e `--architecture`, mantendo os padrões Linux usados pelo CI e
  pelo `install_locked.py`.
- Um teste cobre o roundtrip de manifesto Windows e rejeita manifesto de outra
  plataforma.

## Evidência local

- Venv nova em Windows/AMD64 com CPython 3.14.8.
- Instalação `--require-hashes --only-binary=:all:` dos 54 pacotes; projeto
  editável sem resolução; `pip check` sem conflitos.
- Suíte integral: **2.192 aprovados, 17 ignorados, zero falhas** (7m03s).
- Caminho canônico com `pip` repetido em outra venv 3.14.8: instalação
  hash-checked, projeto editável e `pip check` aprovados; testes de lock/fotos
  passaram.
- Manifesto Windows gravado e verificado; manifesto Linux de 51 pacotes
  continua verificando sem alteração.

## Limites

O lock não é universal: macOS e outras arquiteturas continuam sem lock próprio.
Não houve execução em CI Windows, auditoria de vulnerabilidades, digest de
imagem/navegador ou validação de produção. A Issue #22 permanece aberta para
macOS e para o job de CI; o lock Linux não foi alterado.
