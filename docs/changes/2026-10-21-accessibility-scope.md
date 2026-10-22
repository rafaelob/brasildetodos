<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Escopo de acessibilidade encerrado sem auditoria humana

Lote de 21/10/2026. Código em `a11c48ba5927270271a4ce4e2b8c864287899c34`.

## Decisão

O owner definiu que **não haverá auditoria humana** de leitor de tela, Safari,
dispositivo físico ou reflow/zoom. A Issue #20 foi encerrada como *not planned*
para essa parte. O escopo automatizado abaixo é o aceite final deste repositório;
ele não é uma certificação WCAG e não autoriza a frase “acessível para todos”.

## Evidência automatizada

- `axe-core 4.10.3` WCAG 2.0/2.1 A/AA: zero violações em exploração, ficha e
  colaboração aprovada, em 320/390/1440 px.
- Skip link: primeiro `Tab` alcança o link, `Enter` foca `#main`.
- Landmarks: exatamente um `main`, um `banner`, ao menos uma `navigation` e um
  `h1` em cada largura; verificado pelo `browser_smoke.py`.
- Web: 243 testes aprovados; build Vite 8.2.4.
- Teclado, contraste de tokens, alvos de 44 px e redução de movimento continuam
  cobertos pelos testes existentes.

## Limites

Não houve leitor de tela real, dispositivo físico, Safari/Firefox, zoom/reflow
200%/400%, alto contraste do sistema ou auditoria manual. A cobertura é apenas
Chromium/Edge headless com dados sintéticos. A Issue #20 permanece referenciada
em `docs/ACCESSIBILITY.md`; o mapa WebGL/3D não foi auditado com tecnologia
assistiva.
