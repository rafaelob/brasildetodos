<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Correção dos avisos de certifi e Pillow

Lote de 21/10/2026. Base de integração no `main`: `acbe184`. Código em
`a3dd943`.

## O que mudou

- `certifi` passou de `2026.7.22` para **`2026.10.19`** e `Pillow` de
  `12.3.0` para **`13.0.0`**, corrigindo os avisos GHSA-6q48 e GHSA-8g5g
  reportados na Issue #18.
- O pin de Pillow no `pyproject.toml` e o lock Linux foram atualizados; o
  manifesto foi reemitido com **51 pacotes**.
- O worker documental usa `ops/install_locked.py`, portanto recebe os mesmos
  pins; não há instalação sem lock no `Dockerfile.documents`.
- O README/estado público continua sem prometer que uma varredura de
  vulnerabilidades foi exaustiva.

## Evidência local

- Suíte Python integral em `a3dd943`: **2.189 aprovados, 17 ignorados, zero
  falhas** (7m13s). Dois avisos não bloqueantes.
- Web: **243 aprovados, zero falhas**; build Vite 8.2.4 aprovado.
- Lock Linux: 51 pacotes, instalação hash-checked e `pip check` sem quebra.
- `ops/Dockerfile.documents` reconstruído com o lock novo; o container
  reportou `Pillow 13.0.0` e `certifi 2026.10.19`.
- Renderização real com `pdftoppm` no worker: PNG de 14.169 bytes, SHA-256
  `b7266837f4a1256171deb157c7f3ef1a711ac4ce673ca7b873acfad41aab10ee`.

## Limites

A correção cobre os dois avisos conhecidos e os pins do lock; não é uma
auditoria completa de todas as dependências, imagens ou do sistema operacional.
Não houve deploy de produção. A Issue #18 pode ser encerrada com esta evidência;
Issues #2–#5 continuam abertas.
