<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Acessibilidade

Status em 21/10/2026: **cobertura automatizada parcial**, não certificação WCAG.
O código de referência é `e8703ce`.

## O que foi verificado

- `axe-core 4.10.3` com as tags WCAG 2.0/2.1 A e AA, em Chromium/Edge
  headless, sobre banco e catálogo exclusivamente sintéticos.
- Páginas: exploração, ficha do lugar e colaboração aprovada, nas larguras
  320, 390 e 1440 pixels.
- Resultado local: **zero violações** nas sete varreduras; a execução falha em
  violação `serious` ou `critical` quando `BDT_AXE_FAIL=1`.
- Teclado: o primeiro `Tab` alcança o link “pular para o conteúdo”; `Enter`
  move o foco para `<main id="main" tabIndex={-1}>`.
- A suíte web já cobre alvos de toque de 44 px, contraste dos tokens, redução
  de movimento e presença de rótulos/landmarks em pontos específicos.

## O que não foi verificado

- Leitor de tela real (NVDA, JAWS, VoiceOver, TalkBack) e testes com pessoas.
- Safari, Firefox, dispositivos físicos, zoom de 200%/400%, reflow completo e
  modo de alto contraste do sistema.
- Conformidade WCAG integral ou certificado; axe não substitui auditoria
  manual.
- Mapa WebGL/3D e seus controles com tecnologia assistiva.
- Conteúdo de documentos, OCR, fotos e grupos em todos os estados possíveis.

## Como repetir a varredura

O `axe-core` é ferramenta de auditoria, não dependência de runtime. O script
precisa ser servido na mesma origem por causa da CSP `script-src 'self'`.

```bash
npm --prefix web run build
npm install axe-core@4.10.3 --prefix /tmp/bdt-axe --no-save
cp /tmp/bdt-axe/node_modules/axe-core/axe.min.js web/dist/axe.min.js
BDT_AXE_URL=http://127.0.0.1:8034/axe.min.js BDT_AXE_FAIL=1 python ops/browser_smoke.py
rm web/dist/axe.min.js
```

O `browser_smoke.py` sobe a API e o frontend compilado em `127.0.0.1:8034`,
usa dados sintéticos e apaga o banco temporário. Em Windows, use uma cópia
equivalente em `%TEMP%` e o Edge/Chromium instalado.

## Lacuna aberta

A Issue #20 continua aberta para leitor de tela, dispositivos físicos, Safari e
reflow/zoom. Nenhum resultado acima deve ser lido como “acessível para todos”
ou como cobertura de produção.
