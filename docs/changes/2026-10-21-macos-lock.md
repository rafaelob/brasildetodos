<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Lock macOS arm64 validado

Lote de 21/10/2026. Workflow em `d65876c`; artefatos em
`bb239463233aae38cd1c92f3d6349d15f11c7e55`.

## O que mudou

- `requirements/macos-py314.lock` foi gerado no CPython 3.14.8/arm64 pelo
  workflow manual `.github/workflows/macos-lock.yml`, usando o lock Linux como
  constraint. São **50 pacotes**; os 50 pins comuns são idênticos ao Linux e
  `greenlet` não é resolvido no alvo (runtime síncrono).
- `requirements/macos-py314.json` registra `Darwin`/`arm64`, hashes do lock e do
  pyproject, contagem e instalação verificada.
- O workflow instala `--require-hashes --only-binary=:all:`, instala o projeto
  sem resolução, executa `pip check`, a suíte integral, grava e verifica o
  manifesto. O artefato é baixado e incorporado manualmente; não há commit
  automático.
- Nenhum código de aplicação mudou; o lock é específico de macOS arm64.

## Evidência

Run público [39696830961](https://github.com/rafaelob/brasildetodos/actions/runs/39696830961):
concluído com sucesso em 4m05s no runner `macos-15` arm64.

- Instalação hash-checked dos 50 pacotes.
- Projeto editável e `pip check` aprovados.
- Suíte integral: **2.192 aprovados, 17 ignorados, zero falhas**.
- `record`/`verify` do manifesto `Darwin`/`arm64` aprovados.
- Lock e manifesto baixados do artefato e verificados novamente no checkout.

## Limites

macOS Intel, outras arquiteturas e CI Windows permanecem sem lock/validação
próprios. O lock não é auditoria de vulnerabilidades, não cobre produção e não
é universal. A Issue #22 pode ser encerrada com esta evidência para Windows
AMD64 e macOS arm64; novas arquiteturas exigem regeneração.
