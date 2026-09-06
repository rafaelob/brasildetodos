<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Instalação de recursos públicos verificados

Esta frente é independente do novo módulo de grupos cuja publicação foi bloqueada
pela ferramenta. Não altera autenticação, permissões, dados comunitários ou rotas
da aplicação. Não tenta publicar aquele módulo por outra via.

Objetivo: instalar artefatos públicos minimizados em um banco existente sem
recoletar os originais, apagar cadastros ou inventar versões históricas. O operador
seleciona os hashes externos do relatório e dos registros. A aplicação existente
já permite consultar recursos, filtros, versões, valores exatos e exportações.

## Checklist

- [x] S01 — Conferir o main, o modelo de versões e a verificação dos artefatos.
- [x] S02 — Registrar o plano e manter escopos bloqueados fora desta publicação.
- [ ] S03 — Instalador transacional com cópia congelada dos bytes, hashes externos,
  campos permitidos, identidade/território/fase e histórico idempotente.
- [ ] S04 — Testes de rollback integral, relógio de versão, metadados inválidos,
  duplicação, ausência de remoções, exportação e privacidade das tabelas existentes.
- [ ] S05 — Validar instalação de 6.679 recursos reais no catálogo CNES existente,
  reinstalação e consulta pela API, sem atribuir o reuso a uma nova coleta.
- [ ] S06 — Executar a validação na CI com Python 3.14.7 e manter a suíte/frontend.
- [ ] S07 — Atualizar TODO, ROADMAP, STATUS, evidências e publicação no main.

## Escopo e não-promessas

Reaproveitar a distribuição CNES da execução 34007758949 e os recursos da execução
34048819034 só depois de conferir hashes e o alcance das fontes. Os recursos são
6.677 contratos da janela de publicação 04/09/2026, um plano especial e um projeto
Obrasgov; isso não é toda a despesa pública nacional. Não criar pagamentos,
associações a equipamentos ou localizações de execução a partir do comprador.
A instalação e a API em banco temporário não equivalem a deploy público.

Regressões locais em runtime auxiliar, build/CI em runtime exigido, dados oficiais
e publicação remota são resultados separados. Nenhum novo serviço externo ou LLM
é necessário ao comando de instalação.
