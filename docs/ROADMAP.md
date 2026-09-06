<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Caminho de implementação

A base desta PR é execução real da primeira fatia, não conclusão das 24 horas nem certificação nacional. Não recuar a piloto municipal para ocultar falta de cobertura; entregar cobertura progressiva explicitamente.

## E1 — Certificar ingestão nacional (P0)

- [ ] Obter edições oficiais e dicionários de municípios, escolas e CNES.
- [ ] Validar cabeçalhos reais e implementar perfis de edição adicionais.
- [ ] CNES bulk/paginação terminal comprovada, sem repetir páginas nem depender de amostra default.
- [ ] Manifesto por fonte/UF com total esperado, aceito, excluído, inválido, sem geometria e período.
- [ ] Snapshot nacional com troca atômica e retirada por ausência somente em escopo completo.
- [ ] Benchmarks Postgres, índices textuais e geográficos, fonte de tiles/viewport nacional sem limite da página.
- [ ] Certificação nacional somente após reconciliação; interface apresenta faltas enquanto isso.

## E2 — Recursos e intervenções (P0)

- [ ] Perfis atuais Transferegov, propostas/instrumentos/metas/etapas/assinatura, aditivos e cronologia.
- [ ] Paginação PNCP e revisita de contratos alterados; guardar metadados/documentos e IDs por sistema.
- [ ] Obrasgov current API, geometrias e execução física como declaração da fonte.
- [ ] Editor de vínculos direct/reviewed/territorial/candidate com evidência e histórico.
- [ ] PDDE/FNS com granularidade correta; sem alocar gasto municipal por aproximação.
- [ ] Reconciliação financeira entre fontes, estornos/correções e moeda/período consistentes.

## E3 — Documentos e OCR (P0/P1)

- [ ] Fila isolada, quotas, status/retry/cancel, storage restrito e retenção.
- [ ] Corpus oficial digitalizado licitamente obtido; ground truth de campos, taxa de erro e abstenção.
- [ ] Classificadores determinísticos por família, tabelas multipágina, prazos/aditivos.
- [ ] Editor documento/campo/trecho e revisão independente da associação ao lugar.
- [ ] Tratar dados pessoais, assinaturas e versões derivadas antes de reexibição.

## E4 — Colaboração e operação pública (P0)

- [ ] Migrações evolutivas e teste PostgreSQL real.
- [ ] Fluxo de exclusão/exportação de conta, suporte, recuperação e expiração de rascunhos.
- [ ] Retratação/revisão posterior de observações, justificativas e recurso do autor.
- [ ] OIDC opcional e políticas de moderação com responsáveis.
- [ ] Testes browser automatizados, acessibilidade humana, builds reproduzíveis/lockfiles, auditoria de dependências.
- [ ] Domínio/HTTPS, backups restaurados, deploy e rollback por digest; sem segredos no Git.

## E5 — Experiência territorial (P1/P2)

- [ ] Mapillary/Panoramax opcional com data/licença, sem confundir imagem histórica e visita.
- [ ] Terreno e modelos de obras quando disponíveis; distinguir visualização volumétrica de realidade atual.
- [ ] Grupos de acompanhamento, tarefas e histórico coletivo, sem recompensa a acusações.
- [ ] Upload de fachada apenas após privacidade, remoção EXIF, moderação e pipeline seguro.
- [ ] IBGE setores, acessibilidade/Ipea, conectividade escolar/Giga e outras camadas documentadas.

## Regras de aceite

Não há dados inventados em produção; cada vínculo publicado possui fonte; fases financeiras separadas; contribuições pendentes privadas; original PDF preservado; interface pt/en/es; lista sem mapa; núcleo sem API de LLM. Não afirmar "100% testado" por cobertura de linhas ou por fixtures sintéticas.
