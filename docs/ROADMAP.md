<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Plano vivo de implementação — Brasil de Todos

Atualização: 06/09/2026. Trabalho exclusivamente no `main`, sem force push.
Este plano substitui a lista antiga da PR inicial. `[x]` significa uma entrega
implementada com a evidência indicada; não significa cobertura nacional ou deploy.

## P0 — Catálogo nacional e publicação operacional

- [x] Importação territorial IBGE e reuso de snapshot com proveniência preservada.
- [x] CNES: perfil observado no arquivo oficial, quarentena explícita, relatório
  por UF e pacote público verificável. Evidência: 96.123 elegíveis, 27 UFs, sete
  sem coordenadas, execução `34007758949`; aceite API `34008771230`.
- [x] Inep: descoberta da edição e leitura apenas de tabelas escolares, validação
  de encoding/identidades/ano/município/UF, transação e relatório. 44 testes.
- [ ] Concluir download e ingestão real da edição 2025: tentativas oficiais
  terminaram em ConnectTimeout. Não substituir por amostra ou edição antiga.
- [ ] Certificar cobertura e reconciliação de todas as partições escolares e de
  saúde segundo denominadores publicados. Presença em 27 UFs não é certificado.
- [x] Instalação atômica de pacote público, sem contas, sessões ou observações.
- [x] Agregação do mapa independente da página da lista; contabilidade dos 96.116
  pontos CNES verificada na API. Falta avaliação visual externa e carga simultânea.
- [ ] Atualização periódica, publicação durável do catálogo e alertas de falhas.
- [ ] Domínio/HTTPS, ambiente cloud, operação de backups e rollback exercitado.

## P0 — Recursos, contratos e intervenções

- [x] Editor privado de documentos e vínculos; trecho literal, revisão por outra
  pessoa, publicação e retratação sem alocação automática de dinheiro.
- [x] Inspeção dos OpenAPI PNCP, Transferegov Especiais e Obrasgov atuais no runner
  (`34009291326`). Guardar esquemas e hashes, não inferir contrato de API futura.
- [x] Perfis de metadados: contratos PNCP, planos de ação especiais e projetos
  Obrasgov. Valores exatos, campo `receita`, escopo territorial e dados minimizados.
- [x] Coleta por páginas, retomada, publicação transacional de consulta completa,
  histórico de versões, detecção de regressão/conflito e preservação do anterior.
- [x] API e interface trilíngue de busca de recursos, valores separados e histórico.
  Suíte local nesta rodada: 446 Python, 28 Node. Build e browser aprovados na CI
  `34010614709`: três idiomas e 320/390/1440 px. A falha da coleta/importação
  oficial é registrada separadamente e não tratada como aprovação global.
- [x] Importar e consultar na API um plano Especiais e um projeto Obrasgov reais,
  via consultas completas por identidade. Execução `34010343797`, artefato `9982323950`.
- [ ] Concluir importação PNCP: 6.677 registros recebidos em 14 páginas, mas rollback
  por `invalid_decimal_resource_amount`. Identificar campo/tipo/escala antes de
  definir representação de valores; não arredondar ou transformar em zero.
- [ ] Incluir todos os módulos/tabelas Transferegov: assinatura, instrumentos,
  metas, etapas, aditivos, desembolsos e pagamentos. Plano especial não é convênio.
- [ ] Fila de documentos/anexos referenciados, metadados, hashes e revisão.
- [ ] Geometrias e execução física Obrasgov, sem confundir endereço comprador.
- [ ] PDDE e FNS preservando granularidade e identificação das unidades.
- [ ] Reconciliação entre sistemas, estornos/correções e destinatários; impedir
  dupla contagem. Metadados de contrato/plano não criam lançamento financeiro.
- [ ] Scheduler por janela sobreposta, resposta HTTP 204 explícita, reconciliação
  temporal e monitoramento de esquema. A CLI paginada não é esse scheduler.

## P0/P1 — Documentos e OCR

- [x] Texto nativo, posições, tabelas e candidatos sem publicação automática.
- [x] OCR seletivo local com original preservado, autorização, lease, rollback,
  recuperação de tarefa interrompida e conteúdo privado. 28 testes.
- [x] Uma página digitalizada sintética em português passou por Tesseract real
  (`34008123457`). Prova de integração, não acurácia de corpus governamental.
- [ ] Corpus oficial licitamente obtido e anotado, métricas por campo, abstenção,
  documentos multipágina/assinados, imagens ruins e tabelas fragmentadas.
- [ ] Fila operacional com quotas, cancelamento, retenção e expurgo automático.
- [ ] Classificação por família e extração de aditivos/prazos em corpus real.
- [ ] Política de reexibição, dados pessoais e arquivos derivados validada.

## P0 — Qualidade e colaboração

- [x] Autenticação, CSRF, revisão independente, exportação/desativação de conta,
  retirada de contribuição e retratação de vínculos documentais.
- [x] Browser nos três idiomas e em 320/390/1440 px: testes de colaboração e fluxo
  documental, corrigindo falhas sem retirar gates (`34008376092`).
- [x] PostgreSQL temporário e container não-root/read-only no runner; backup SQLite
  com WAL e restauração em destino novo. Não equivalem à operação cloud validada.
- [ ] Lockfiles transitivos revisados e incorporados, build reproduzível e gates
  de vulnerabilidades com exceções justificadas (diagnóstico não basta).
- [ ] Acessibilidade com leitor de tela, Safari/dispositivo físico, carga e índices.
- [ ] Responsáveis de moderação, recurso do autor, recuperação de conta e retenção.

## P1/P2 — Experiência territorial e expansão

- [ ] Panoramax/Mapillary opcionais com data e licença; imagem histórica != visita.
- [ ] Testar tiles/3D reais e versões para dispositivo limitado, sem bloquear lista.
- [ ] Grupos, tarefas e histórico coletivo sem incentivar acusações.
- [ ] Fotos apenas após remoção EXIF, revisão, exclusão e política operacional.
- [ ] IBGE setores, Ipea/acesso, conectividade escolar/Giga e camadas globais.
- [ ] Auditoria de licença por fonte, documentação de contribuição e governança.

## Ordem seguinte e definição de conclusão

1. Executar e reconciliar os conectores oficiais estritos; registrar bloqueios.
2. Fechar educação nacional e publicações periódicas com logs verificáveis.
3. Completar cadeia de instrumentos/documentos/financeiro e revisão de vínculos.
4. Validar experiência territorial, desempenho, operação pública e deploy.

Não usar percentual global de “pronto”. Reportar separadamente código publicado,
testes executados, dados efetivamente importados e aplicação acessível ao público.
Ver `RESOURCE_INGESTION.md`, `MAIN_IMPLEMENTATION_20260906.md`, `DATA.md` e `STATUS.md`.
