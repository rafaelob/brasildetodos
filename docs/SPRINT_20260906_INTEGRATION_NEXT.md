<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Próximo lote — integração pública, dados verificáveis e validação

Base inspecionada: `a3ecad0be179e128fed45f7602859e6d47a80137`.
Trabalho somente no main, preservando alterações concorrentes e sem force push.
Python 3.14.7 / Node 24.20.0. Nenhum LLM obrigatório.

## Decisões e evidência de partida

A coleta oficial 34048819034 já passou antes deste lote: 6.677 contratos PNCP
na janela de publicação 04/09/2026, um plano Transferegov e um projeto Obrasgov.
O artefato 9993985086 tem SHA-256
`f37be95dad644bd784abf75895e872122cd26815192e10552a6e9c6577a94cd8`.
Isso não certifica cobertura nacional de recursos ou implantação pública.
O TODO ainda cita a falha antiga; será reconciliado, preservando o histórico.
Os módulos de acompanhamento e cobertura já existem isoladamente: não serão
reescritos nem atribuídos a este lote como se fossem novos.

## Checklist de execução

- [x] B01 — Ler main, AGENTS e TODO; obter e conferir o snapshot da revisão.
- [x] B02 — Registrar este plano antes de modificar a aplicação.
- [ ] B03 — Integrar consulta limitada de Meus lugares e cobertura pública,
  preservando autenticação/CSRF das escritas e evitando rotas duplicadas.
- [ ] B04 — Integrar interface de favoritos/histórico e cobertura/importações,
  com estados independentes, filtros, paginação e textos PT-BR/EN/ES.
- [ ] B05 — Testar projeções públicas, ausência de escrita, limites, registros
  sem coordenadas, perfis alterados e recuperação de falhas nas rotas reais.
- [ ] B06 — Implementar instalação transacional dos recursos minimizados de um
  artefato verificado, sem inventar versões passadas, pagamentos ou vínculos.
- [ ] B07 — Validar instalação/reinstalação/rollback e consultar os dados reais
  pela API; distinguir reuso de artefato de nova coleta oficial.
- [ ] B08 — Executar build e jornadas nativas de navegador nos três idiomas em
  320/390/1440 px; preservar os percursos existentes e inspecionar capturas.
- [ ] B09 — Reexecutar a coleta educacional oficial ou registrar o impedimento
  concreto; não substituir silenciosamente por edição anterior ou amostra.
- [ ] B10 — Rodar a suíte completa, conferir runtimes e CI do código publicado.
- [ ] B11 — Atualizar TODO, ROADMAP e STATUS com resultados separados de código,
  testes, dados e deploy, incluindo todas as frentes ainda abertas.
- [ ] B12 — Confirmar commits e referência main após publicação sem force push.

## Pendências maiores mantidas

Ingestão escolar nacional e denominadores; demais tabelas Transferegov e FNS/PDDE;
reconciliação de pagamentos/aditivos/estornos; corpus oficial OCR; imagens e
panoramas; mapas/3D externos; grupos e moderação operacional; acessibilidade
assistiva/dispositivos; ambiente público, domínio, backups e atualização periódica.
Essas entregas não são encerradas por concluir as jornadas deste lote.

## Critérios de conclusão

Nenhuma chave de IA, dados sintéticos de produção ou vínculo por proximidade.
Datas de coleta e referência distintas; dados carregados não significam serviço
em funcionamento. Sucesso de teste isolado não certifica integração. Código
publicado não significa deploy. Só marcar cada item após a evidência respectiva.
