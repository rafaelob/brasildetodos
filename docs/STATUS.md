<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Estado verificado — fechamento de grupos, OCR e distribuição

Atualizado em 20/10/2026 (America/Sao_Paulo). Somente main; sem force push.
Código verificado do fechamento de grupos/OCR/`public-data`:
`8324b7620021e1c5bb3a32e7439026a3a0067af2`.
Plano inicial deste fechamento: `ec753635779d473c16105832ee36302c92352451`.
Reconciliação educacional em 09/09/2026: o fechamento acima não inclui escolas;
a release `education-2025-20260907-v1` é posterior e está na seção escolar.

## Lote de 20/10/2026 — integridade e fila OCR

O `main` integrou, por merges locais sem force push, as nove fatias corretivas das
Issues #2–#5. O lote acrescentou fila OCR persistente e privada, metadados
opcionais de edição/licença no catálogo, partições municipais verificáveis,
contadores de leitura/aceitos/excluídos na cobertura, filtro `has_geometry`,
validação do pacote de extração na leitura de página e registro de
`public_excerpt_checked` na auditoria. A fila não armazena bytes nem texto e não
publica automaticamente; o Workbench permite enfileirar, cancelar e repetir com
i18n pt-BR/en/es.

Código deste lote: `59a02f2bdabefdbeeac4e1f757a903084d9525ef`.
Evidência local em Python 3.14.8 e Node 24.20.0: suíte Python integral com
**2.138 aprovados, 17 ignorados e zero falhas**; web com **243 aprovados**;
build TypeScript/Vite aprovado; `npm audit --audit-level=high` com zero
vulnerabilidades. O checkout Windows também preserva os bytes de
`pyproject.toml`, do lock Linux e do corpus OCR versionado.

A verificação dos releases publicados também foi repetida com o código deste lote.
`public-data-20260906-v1` (28.096.042 bytes, SHA-256 `6d62f9ca...cc1639`) passou
com 96.123 lugares, 6.679 recursos, 0 eventos financeiros, 0 usuários e 0
observações; `education-2025-20260907-v1` (23.807.757 bytes, SHA-256
`483bba3a...5fcfe7`) passou com 214.192 lidos, 138.086 elegíveis, 76.106
excluídos e 27 UFs. Nos dois casos a API foi consultada, o banco existente não foi
modificado e `public_deployment` ficou **falso**; a verificação escolar manteve
`browser_checked` **falso** e `national_completeness_certified` **falso**. O ZIP
de saúde/recursos também passou nos aceites de catálogo público e de recursos
combinados, com replay idempotente e 55 registros de valores subcent.

O lote corrigiu ainda a compatibilidade do fingerprint com releases legados e
removeu do teste de mapa o `page.wait_for_function` com string, bloqueado pela CSP
`script-src 'self'`. Nenhuma dessas correções certifica cobertura nacional.

Os oito workflows executados no `main` a partir do commit `9f45f85` passaram: Quality
`39528907182` (com navegador), Runtime integration `39528907133`, Public catalog
API acceptance `39528907180`, Combined public resource release `39528907240`,
Published data and OCR acceptance `39528907224`, Unified national catalog
acceptance `39528907186`, Verified national education release `39528907199` e
Durable reviewed public data `39528945450`. Os aceites de catálogo e recursos
usaram o ZIP publicado e conferiram tamanho/SHA-256.

A execução local não abriu navegador; o Quality no runner executou os percursos.
Este lote não executou ingestão oficial nova, avaliação de corpus oficial,
PostgreSQL durável, migração Alembic nem deploy. A certificação nacional continua
**falsa** e as Issues #2–#5 continuam abertas. Detalhes em
`changes/2026-10-20-integrity-and-ocr-queue.md`.

## Resultado

O lote de grupos integrados, preservação do material de OCR e distribuição
verificável está fechado. Grupos, corpus e release já tinham sido publicados
antes desta retomada; a última resposta da conversa estava desatualizada.
O fechamento preservou esse trabalho e acrescentou instalação atômica do pacote
completo, seleção externa dos bytes, verificação contínua e regressões.
Não existe declaração de conclusão integral nem de deploy público.

## Evidência da revisão

| Verificação | Resultado |
|---|---|
| Quality `34076805060` | Aprovada: backend, testes web, build TypeScript/Vite e doze percursos de navegador |
| Backend | 929 testes aprovados, zero falhas, erros ou skips; 3.996/4.178 linhas cobertas (95,64%); piso 85% preservado |
| Web | Suíte Node aprovada e build completo em Node 24.20.0; 187 testes também conferidos na execução auxiliar |
| Runtime `34076805106` | Aprovado: PostgreSQL temporário, container real não-root/read-only e frontend servido |
| Release/corpus `34076805501` | Aprovado em Python 3.14.7: download dos bytes publicados, instalação integral e consulta da API |
| Acervo OCR versionado | Seis arquivos, quatro originais; hashes preservados e extração nativa conferida; nenhuma nova execução de OCR |

Os relatórios JUnit/cobertura e do aceite foram baixados e seus SHA-256 conferidos.
Identificadores, contagens, hashes e escopos estão em
`reports/20260906-verified-closeout.json`. Cobertura de linhas não mede branches.
A suíte completa local foi interrompida por limite de execução; a aprovação acima
é da revisão publicada no runner, não uma extrapolação dos testes auxiliares.

## Grupos e frontend

A interface usa a API `/groups` publicada, não o rascunho antigo `/community`.
O percurso nativo cria grupo, gera convite de uso único, ingressa com outra conta,
seleciona lugar no catálogo, cria/assume tarefa, registra observação privada,
compartilha explicitamente e revisa por outra pessoa. Recarregar conserva estado;
retirar a observação revoga sua disponibilidade no grupo; sair revoga o acesso.
Aceitar no grupo não publica a observação. Tokens não entram em URLs nem no export.

Os doze percursos preservados abrangem também consulta, favoritos, documentos,
privacidade, recursos, comparação, exportação, respostas atrasadas, mapa opcional,
visita guiada, cobertura e descoberta municipal. As combinações específicas estão
nos scripts `ops/browser_*.py`; o fluxo de grupos cobre pt-BR/en/es em 320/390/1440.
API e persistência dos percursos são reais, mas as contas/dados desses testes são
sintéticos, isolados e descartados. Não são cidadãos reais ou dados de produção.

## Dados e OCR no GitHub

`tests/corpus/ocr-reviewed/` contém `SYNTHETIC-native.pdf`, `SYNTHETIC-scanned.pdf`,
`SYNTHETIC-page.png`, `result.json`, `native-extraction.json`, `recognized-text.txt`
e o manifesto. São os materiais sintéticos anteriormente usados na validação
portuguesa. Não existem convênios oficiais disfarçados de fixtures nesse acervo.

A release `public-data-20260906-v1` contém 96.123 estabelecimentos CNES elegíveis
no perfil de atendimento ambulatorial SUS declarado, sete sem coordenadas, e
6.679 recursos (6.677 contratos PNCP da janela de 04/09/2026, um plano especial,
um projeto Obrasgov). O arquivo tem 28.096.042 bytes e hash externo fixado em
`data/releases/public-data-20260906-v1.json`. O novo instalador reproduziu as
contagens em banco novo e protegeu as rotas privadas da API.

O pacote não contém contas, sessões, grupos ou observações. Tem zero eventos
financeiros na tabela finance: valores cadastrais de contratos/planos não viram
pagamentos. A release é uma prévia de dados com seleção por hash; imutabilidade
administrativa do GitHub está desabilitada. Ver `BUNDLE_INSTALLATION.md`.

## Coleta escolar: incidente TLS de 06/09/2026 e release 07/09/2026

Em 06/09/2026 a execução `34069973954` encontrou o link oficial da edição 2025,
mas a conexão de download falhou com `SSLCertVerificationError`, código 20; não
foi falha DNS nesse diagnóstico. A inspeção `34070468415` não alterou confiança
nem desabilitou TLS e não baixou o dataset. Recibos:
`reports/20260906-education-transport-e0943f9.json` e
`reports/20260906-inep-tls-cb873ed.json` (`collector_verification_disabled`
falso). O fechamento `8324b762` revalidou `public-data-20260906-v1` e não
incluiu escolas.

Em 07/09/2026 a release `education-2025-20260907-v1` foi publicada a partir da
coleta `34078768110`, revisão `96aa4bf80cc13402f0d35d47a8deabcae6d30db3`:
138.086 escolas públicas declaradas ativas, 0 geometria, registros nas 27 UFs;
seleção `data/releases/education-2025-20260907-v1.json`. Presença nas 27 UFs não
certifica completude; denominadores oficiais seguem abertos. Essa publicação não
substitui `public-data-20260906-v1` (96.123 lugares CNES, 6.679 recursos, tabela
finance 0). A união dos ZIPs não é KPI de instalação viva nem deploy público.

## Pendências reais

Denominadores escolares/CNES e atualização periódica; transporte TLS verificado
para edições futuras; nova competência CNES; demais módulos
Transferegov/Obrasgov/PDDE/FNS e reconciliação financeira; corpus oficial de OCR,
fila e retenção; fotos/panoramas; mapas externos; recuperação de conta/moderação;
acessibilidade assistiva/dispositivos; segurança e desempenho; implantação pública
com HTTPS, armazenamento durável, monitoramento e recuperação.
Detalhamento executável: Issues #2–#5 no GitHub; visão: `ROADMAP.md`; matriz: `FEATURE_MATRIX.md`.
O texto anterior permanece intacto em `history/STATUS_89584b82.md`.
