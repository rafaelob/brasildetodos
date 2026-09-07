<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# TODO executável — Brasil de Todos

Atualizado em 06/09/2026 (America/Sao_Paulo). Código de fechamento: `8324b762`.
Trabalho somente no main; Python 3.14.7 / Node 24.20.0; sem force push.
O estado anterior foi preservado em `docs/history/TODO_89584b82.md`. Suas falhas
são registros históricos, não a situação atual. O projeto inteiro não está
concluído: este documento fecha o lote de grupos/acervo/publicação e explicita
os requisitos restantes, sem apagá-los ou escondê-los em mocks.

## Lote atual — fechado com evidências

Plano: `docs/SPRINT_20260906_VERIFIED_CLOSEOUT.md`. Relatório e identificadores:
`docs/reports/20260906-verified-closeout.json`.

- [x] V01 Conferir main/AGENTS; validar hash e árvore do snapshot, preservando alterações concorrentes.
- [x] V02 Confirmar grupos persistentes e navegação integrada no contrato `/api/groups`; não reaplicar o rascunho incompatível `/community`.
- [x] V03 Verificar criação/convite/ingresso/tarefa/observação própria/revisão independente/recarga/retirada/saída com dois usuários no navegador, em pt-BR/en/es e 320/390/1440 pixels.
- [x] V04 Confirmar os quatro originais sintéticos usados no OCR e dois derivados, com manifesto e hashes, já versionados em `tests/corpus/ocr-reviewed/`.
- [x] V05 Exigir verificação offline do acervo real versionado em toda CI Quality; a verificação não faz rede nem nova execução de OCR.
- [x] V06 Fixar identidade, tamanho, hash externo, entradas e contagens da release pública em `data/releases/public-data-20260906-v1.json`.
- [x] V07 Implementar instalação integral catálogo + recursos em banco SQLite novo, com snapshot privado, integridade, checkpoint e publicação atômica sem sobrescrita.
- [x] V08 Testar rollback de instalação, corrupção, seleção divergente, corrida de destino, troca de origem, sidecars e ausência de dados privados; 35 regressões novas e 64 testes específicos aprovados.
- [x] V09 Baixar a release efetivamente publicada, instalar todos os registros e consultar a API em Python 3.14.7; aceite `34076805501` aprovado.
- [x] V10 Aprovar suíte completa de 929 testes Python, 95,64% de cobertura de linhas, build e doze percursos de navegador; Quality `34076805060`.
- [x] V11 Aprovar integração PostgreSQL/container `34076805106`; não apresentar ambiente temporário como deploy público.
- [x] V12 Publicar implementação no main, reconciliar TODO/ROADMAP/STATUS/matriz e preservar separadamente os resultados reais de coleta.

## Entregas anteriores agora confirmadas, não reimplementadas

- [x] Catálogo territorial e CNES instalável, com perfil, fonte, referência temporal e ausência de coordenadas explícita.
- [x] Pesquisa, favoritos, acompanhamento de versões e comparação limitada de lugares; respostas atrasadas e falhas independentes tratadas nos percursos existentes.
- [x] Minha região: descoberta municipal, resumo dos dados carregados e passagem de filtros à pesquisa.
- [x] Cobertura cadastral e histórico paginado de importações integrados; não são certificação de cobertura nacional.
- [x] Recursos: busca/filtros, objetos completos, versões, comparação, compartilhamento e exportação individual/histórica/de seleção.
- [x] Precisão de até quatro casas decimais no perfil PNCP, sem converter valores de contratos em pagamentos.
- [x] Janela PNCP de 04/09/2026 corrigida e importada: 6.677 contratos, mais um plano especial e um projeto Obrasgov na distribuição. O antigo `invalid_resource_text` não é mais bloqueio dessa janela.
- [x] Documentos privados: extração nativa, candidatos, OCR seletivo e vínculos por trecho literal com revisão independente; sem publicação automática.
- [x] Grupos privados: convites de uso único, membros, tarefas, revisão, saída, transferência/arquivamento e controles de privacidade.
- [x] Release de dados públicos `public-data-20260906-v1` publicada com 96.123 lugares e 6.679 recursos; validação novamente executada no fechamento.
- [x] Locks Python/Linux e npm publicados e usados nos jobs-alvo; auditoria completa de todas as dependências e plataformas é requisito distinto abaixo.

## Próximo lote — dados reais e operação

### P0. Educação nacional e atualização dos catálogos

- [ ] D01 Resolver a falha de validação TLS observada no download oficial do Inep, mantendo hostname/CA/HTTPS verificados. Diagnóstico `34069973954`: `SSLCertVerificationError`, código 20. Inspeção `34070468415` não baixou o dataset nem alterou confiança.
- [ ] D02 Baixar e importar as tabelas escolares da edição 2025, sem registros individuais de alunos/docentes, preservando ZIP, hashes, dicionário e referência da edição.
- [ ] D03 Reconciliar contagens elegíveis/excluídas/quarentena por UF/município contra denominadores da fonte. Não concluir completude apenas pela presença nas 27 UFs.
- [ ] D04 Validar nova competência CNES e política de atualização; distinguir cadastro ativo, atendimento SUS declarado e atendimento disponível agora.
- [ ] D05 Programar coleta incremental com revisitas, janelas sobrepostas, alteração de esquema, retomada e indicadores de atraso; preservar a versão válida anterior.
- [ ] D06 Publicar nova edição de dados somente após aceite independente; nova tag e seleção de bytes, sem substituir silenciosamente a v1.

### P0. Recursos e reconciliação financeira

- [ ] F01 Ampliar Transferegov para instrumentos assinados, metas, etapas, aditivos, desembolsos e pagamentos, com identidade e significado por tabela.
- [ ] F02 Integrar execução física e geometrias Obrasgov por identidade do projeto; endereço do comprador não é localização da obra.
- [ ] F03 Integrar PDDE e FNS com identificadores e granularidade efetivamente publicados.
- [ ] F04 Reconciliar destinatários, estornos, correções e eventos entre fontes; provar ausência de dupla contagem sem somar fases financeiras.
- [ ] F05 Processar anexos referenciados em fila, com limites, hashes, revisão e retenção. Vínculos a unidades exigem evidência, não semelhança de nome.

### P0/P1. Documentos, colaboração e experiência

- [ ] O01 Obter e revisar corpus oficial de documentos, com condições de reutilização, minimização e anotação independente.
- [ ] O02 Medir extração e OCR por campo/família, incluindo tabelas multipágina, assinaturas, imagens ruins e abstenção; testes sintéticos não estimam acurácia real.
- [ ] O03 Completar quotas, cancelamento, expurgo, retenção e observabilidade da fila documental em ambiente operacional.
- [ ] U01 Fotos: envio, remoção de metadados, minimização/redação, revisão, exclusão e política operacional antes de publicação.
- [ ] U02 Panoramax/Mapillary opcionais, licença, data de captura e ausência de cobertura; imagem histórica nunca é apresentada como visita atual.
- [ ] U03 Validar tiles e 3D com fonte externa e hardware limitado; lista, busca e contribuição devem continuar independentes.
- [ ] U04 Completar recuperação de conta, recurso de moderação, tratamento de abuso e retenção dos dados de grupos/backups.
- [ ] U05 Validar acessibilidade assistiva, Safari/iOS e Android físicos, zoom/reflow e consumo de memória; percursos Chromium não substituem essas avaliações.

### P0. Implantação e qualidade operacional

- [ ] P01 Implantar backend/frontend com banco e documentos duráveis, HTTPS, domínio e configuração de menor privilégio; publicar URL e revisão real.
- [ ] P02 Exercitar backup/restauração, reconciliação de exclusões, rollback, monitoramento e alertas no ambiente implantado.
- [ ] P03 Medir consultas e concorrência sobre base nacional real; avaliar índices, limites de memória e filas, sem inferir capacidade a partir de um smoke test.
- [ ] P04 Auditar vulnerabilidades/licenças Python e npm, imagens por digest, navegadores e pacotes de sistema; documentar exceções e renovação.
- [ ] P05 Validar perfis Windows/macOS e arquiteturas adicionais; não rotular o lock Linux como universal.
- [ ] P06 Integrar camadas IBGE detalhadas/conectividade/Giga e outras fontes abertas somente após caso de uso, licença e joins revisados.

## Regras de aceite

Cada tarefa fecha com código + teste + evidência da revisão. Coleta, distribuição
de dados, execução de testes e aplicação em produção são quatro coisas distintas.
Não há LLM obrigatório, coordenadas inventadas, resultados sintéticos em produção,
publicação automática de observações nem vínculo de contrato por proximidade.
