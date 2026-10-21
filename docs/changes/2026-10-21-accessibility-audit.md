<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Auditoria automatizada de acessibilidade

Lote de 21/10/2026. Base de integração no `main`: `aeab784`. Código em
`e8703ce7ab571c73e76cf65619304a9210a017d6`.

## O que mudou

- `<main id="main">` recebeu `tabIndex={-1}`. O link “pular para o conteúdo”
  agora move o foco de verdade para o conteúdo principal, não apenas a rolagem.
- O `browser_smoke.py` passou a verificar, nas três larguras, que o primeiro
  `Tab` alcança o link, que ele fica visível e que `Enter` foca `#main`.
- O mesmo script aceita `BDT_AXE_URL` apontando para `axe-core` servido na
  mesma origem (a CSP bloqueia script inline). Com `BDT_AXE_FAIL=1`, falha em
  violação `serious` ou `critical`; o relatório inclui todas as violações.
- A limpeza do servidor temporário não é mais pulada se o navegador já estiver
  fechado, evitando processo órfão na porta 8034.
- O teste de contrato do skip link passou a exigir o alvo focável.

## Evidência local

- `axe-core 4.10.3`, WCAG 2.0/2.1 A/AA, Chromium/Edge headless.
- Exploração, ficha e colaboração aprovada em 320, 390 e 1440 px: **zero
  violações** nas sete varreduras.
- Teclado: `Tab` → skip link, `Enter` → `#main`; aprovado nas três larguras.
- Web: **243 testes aprovados**, build Vite 8.2.4 aprovado.
- O relatório da execução inclui `axe` e `skip_link: true` por viewport.

## Limites

Não houve leitor de tela real, dispositivo físico, Safari/Firefox, zoom/reflow
200%/400%, alto contraste do sistema ou auditoria manual completa. Axe não
substitui avaliação humana e não certifica WCAG. A Issue #20 permanece aberta
para essas lacunas; o mapa WebGL/3D não foi auditado com tecnologia assistiva.
