<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Acessibilidade

Status em 21/10/2026: **escopo automatizado concluído por decisão do owner**;
não é certificação WCAG. O código de referência é `a11c48b`.

## O que foi verificado

- `axe-core 4.10.3` com as tags WCAG 2.0/2.1 A e AA, em Chromium/Edge
  headless, sobre banco e catálogo exclusivamente sintéticos.
- Páginas: exploração, ficha do lugar e colaboração aprovada, nas larguras
  320, 390 e 1440 pixels.
- Resultado local: **zero violações** nas sete varreduras; a execução falha em
  violação `serious` ou `critical` quando `BDT_AXE_FAIL=1`.
- Teclado: o primeiro `Tab` alcança o link “pular para o conteúdo”; `Enter`
  move o foco para `<main id="main" tabIndex={-1}>`.
- Estrutura de leitor de tela: o smoke exige exatamente um `main`, um `banner`,
  ao menos uma `navigation` e um heading de nível 1 em cada largura.
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

## Escopo encerrado e limites

O owner decidiu em 21/10/2026 que **não haverá auditoria humana** de leitor de
tela, Safari, dispositivo físico ou reflow/zoom neste projeto. O escopo
automatizado acima é o aceite final; a Issue #20 foi encerrada como *not
planned* para a parte humana. Isso não autoriza dizer que o produto é
“acessível para todos”, que cumpre WCAG integralmente ou que foi validado em
produção. Teclado, skip link, landmarks, axe A/AA e os testes web são a
evidência disponível.
