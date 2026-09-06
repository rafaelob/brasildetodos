<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Lote integral: territorio, colaboracao e operacao de dados

Base inspecionada: `893795c502032f808ba14201c974511b84bb9013`.
Python 3.14.7 / Node 24.20.0. Trabalho exclusivamente em main, sem force push.
Este plano complementa e preserva os planos anteriores; nenhum check representa
conclusao global, coleta nacional completa ou deploy sem evidencia especifica.

## Inventario e sequencia de execucao

- [x] E01 — Conferir main, AGENTS, TODO e snapshot; identificar funcionalidades
  realmente integradas e preservar incrementos concorrentes e locks existentes.
- [ ] E02 — Completar descoberta municipal nacional pesquisavel e paginada,
  incluindo cidades sem equipamentos carregados. Resumo consistente de servicos,
  geometrias e recursos separados por escopo, com origem e datas.
- [ ] E03 — Entregar Minha regiao no frontend: navegacao, pesquisa por nome/codigo,
  filtros, paginas, carregamento/erro/retentativa, teclado e PT-BR/EN/ES.
- [ ] E04 — Entregar grupos privados persistentes, convites com aceite/expiracao,
  membros, tarefas vinculadas a lugares, entrega e revisao independente. Nao
  alterar publicacao moderada existente nem atribuir privilegios de revisor.
- [ ] E05 — Integrar colaboracao a exportacao/desativacao de conta e retirada de
  evidencias, com quotas, controle de versao, auditoria e nenhuma exposicao publica.
- [ ] E06 — Entregar interface colaborativa completa nos tres idiomas, com estados
  de erro/retentativa e fluxo utilizavel entre pessoas, sem fixtures de producao.
- [ ] E07 — Melhorar coleta oficial segundo os erros observados: tentativas
  limitadas, recuperacao e publicacao apenas apos verificacao. Nao contornar
  restricoes, mudar ano silenciosamente ou inventar proveniencia.
- [ ] E08 — Executar workflows oficiais pertinentes, verificar artefatos por
  bytes/hash/contagem e consultar dados reais. Distinguir nova coleta de reuso.
- [ ] E09 — Criar e executar regressao backend, JS e jornadas nativas de navegador
  nos runtimes exatos; preservar cobertura, testes anteriores e locks revisados.
- [ ] E10 — Auditar e reconciliar TODO/ROADMAP/STATUS por feature, dados, teste e
  operacao. Registrar bloqueios especificos e evidencias dos checks concluidos.
- [ ] E11 — Publicar lotes atomicos diretamente no main, conferir concorrencia,
  SHA remoto e CI. Nunca usar o sucesso de outra revisao como prova deste lote.

## Frentes que devem permanecer visiveis ate validacao completa

1. Educacao nacional 2025, denominadores e atualizacao do CNES.
2. Descoberta municipal, fichas, favoritos, comparacoes e acompanhamento.
3. Instrumentos/metas/etapas/aditivos/transferencias/pagamentos Transferegov,
   execucao fisica/geometrias Obrasgov, PDDE/FNS e conciliacao entre fontes.
4. Documentos/anexos, OCR oficial avaliado por campo, fila, quotas e retencao.
5. Mapa/3D com dados externos, panoramas, acessibilidade assistiva e dispositivos.
6. Grupos/tarefas, fotos, moderacao, recuperacao de conta e retencao operacional.
7. Publicacao duravel, atualizacao periodica, monitoramento, backup/restauracao,
   HTTPS, dominio e implantacao publica em infraestrutura autorizada.
8. Licencas por fonte, contribuicoes, seguranca e dependencia reproduzivel.

## Criterios transversais

Producao usa implementacoes reais, nunca respostas mockadas ou dados de exemplo.
Fixtures isoladas permanecem nos testes para reproduzir erros e concorrencia.
Sem LLM obrigatorio, coordenadas inventadas, vinculo por proximidade, soma de
fases financeiras ou interpretacao de ausencia como inexistencia do servico.
Grupos privados nao sao canal oficial de denuncia. Conclusao de tarefa nao
certifica funcionamento, qualidade tecnica ou acessibilidade de um lugar.
Dados oficiais e observacoes cidadas continuam identificados separadamente.
