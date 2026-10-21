<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Fotos aprovadas em grupos privados

Lote de 21/10/2026. Base de integração no `main`: `19bfde8`. Código em
`244df190f547487017d2ad198adbcc2d73ee3dec`.

## O que mudou

- A entrega de uma tarefa compartilhada (`share_with_group: true`) agora inclui
  as fotos **aprovadas** da observação no payload do grupo. Fotos pendentes,
  rejeitadas, retratadas, expurgadas, de outra observação ou de autor desativado
  não aparecem.
- `GET /api/groups/{group}/tasks/{task}/photos/{photo}/image` exige membro
  ativo, tarefa do grupo, observação ainda visível e a mesma foto aprovada.
  Responde JPEG com `no-store`; qualquer falha é 404 sem revelar existência.
- O membro pode ver a foto mesmo quando a observação ainda está pendente de
  publicação na plataforma. Isso é leitura privada de grupo, não publicação:
  `/api/public/photos/{id}/image` continua exigindo observação publicada.
- O Workbench de grupos renderiza as fotos com crédito, data informada,
  licença, texto alternativo e fallback quando a foto foi retirada entre o
  carregamento e a imagem.
- O consentimento de compartilhamento passou a mencionar explicitamente a
  observação **e suas fotos aprovadas** em pt-BR, en e es.
- Retirada da observação, retratação da foto, saída/remoção do membro e
  desativação da conta encerram o acesso imediatamente. A flag
  `BDT_PHOTO_UPLOADS=1` continua necessária; desligada, a rota responde 404.
- Nenhuma coluna nova: o consentimento existente da tarefa (`observation_id` +
  `share_with_group`) é o gate; não foi inventado um opt-in separado.

## Evidência local

- Suíte Python integral em `244df19`: **2.192 aprovados, 17 ignorados, zero
  falhas** (6m47s). Dois avisos não bloqueantes.
- `backend/tests/test_groups.py`: **37 aprovados**, incluindo membro, não
  membro, foto pendente, retratada, observação retirada e uploads desligados.
- Web: **243 aprovados, zero falhas**; build Vite 8.2.4 aprovado.
- Teste de comportamento confirma que a foto aprovada aparece para o grupo,
  não aparece em `/api/public/photos`, e desaparece após retratação/retirada.

## Limites

Membros ainda podem salvar ou fotografar a tela; `no-store` não impede cópia
local. Não há detecção automática de rosto, política de retenção/expurgo,
moderação operacional de abuso, panorama ou licença de imagem de terceiros.
O grupo não publica a observação e não substitui a moderação da plataforma.
A Issue #5 permanece aberta.
