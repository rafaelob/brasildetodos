<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Matriz de capacidades e limites verificáveis

Referência de código deste lote: `d6c26a6`; execuções e hashes anteriores em
`reports/20260906-verified-closeout.json`, evidência do lote documental em
`docs/changes/2026-10-20-document-structure-and-link-field.md`, dos documentos
PNCP privados em `docs/changes/2026-10-21-pncp-private-documents.md`, dos
originais documentais em `docs/changes/2026-10-21-document-originals.md`, dos
sinais de privacidade em `docs/changes/2026-10-21-privacy-signals.md`, da
limpeza de órfãos em `docs/changes/2026-10-21-private-store-retention.md`, da
verificação de integridade em
`docs/changes/2026-10-21-private-store-verify.md`, da prévia de página em
`docs/changes/2026-10-21-original-page-render.md`, das provas PostgreSQL/Poppler
em `docs/changes/2026-10-21-runtime-proofs.md`, do baseline Alembic em
`docs/changes/2026-10-21-alembic-baseline.md`, do stack PostgreSQL local em
`docs/changes/2026-10-21-local-postgres-compose.md` e das correções de
migração/store em `docs/changes/2026-10-21-migration-store-safety.md`.
Catálogo escolar posterior:
`education-2025-20260907-v1`, seleção
`data/releases/education-2025-20260907-v1.json`. Nenhum status significa
conclusão integral do projeto. Implementação, aceite do software, cobertura e
produção são colunas conceitualmente distintas. Dados sintéticos existem apenas
em testes.

| Capacidade | Implementação/aceite disponível | Lacuna que permanece |
|---|---|---|
| Consulta de lugares e fichas | API e UI; fonte, ID, datas, ausência de geo; browser smoke | Atualidade/completude dos cadastros |
| Favoritos e acompanhamento | Consulta em lotes, histórico, comparação, remoção e recuperação; browser catalog | Favoritos são locais, não sincronização entre aparelhos |
| Comparar lugares | Seleção limitada e informações com fontes; browser comparison | Não produz ranking nem comparação causal |
| Minha região | Diretório municipal, busca e resumo; browser regions | Não certifica disponibilidade de todos os serviços do município |
| Cobertura e importações | Painel e histórico paginado integrados; contadores `read`/`accepted`/`excluded`; filtro `has_geometry` | Denominadores oficiais reconciliados para certificação nacional |
| CNES | Pacote com 96.123 elegíveis, sete sem coordenadas, consulta aceita | Nova competência e validação do perfil/denominadores |
| Educação | Leitor nacional e validações; `education-2025-20260907-v1` com 138.086 escolas públicas ativas, 0 geometria, 27 UFs; seleção `data/releases/education-2025-20260907-v1.json` | Incidente Inep 06/09/2026: `SSLCertVerificationError` código 20 (`reports/20260906-inep-tls-cb873ed.json`); TLS não desabilitado. 27 UFs não é completude; denominadores abertos |
| Recursos PNCP | Janela de 6.677 contratos importada; precisão e objetos preservados; coletor privado de documentos oficiais com bytes content-addressed, SHA-256, revisões e `not_listed` em listagem completa; consumidor reviewer-only de metadados sem bytes | Histórico nacional completo, atualização recorrente, retenção/limpeza operacional, publicação revisada e reconciliação |
| Transferegov/Obrasgov | Perfis de plano especial e projeto; conectores bounded de Parcerias/empenhos e ObrasGov; consumidores reviewer-only de empenhos especiais, PDDE, cabeçalho e empenhos de parceria, execução física e catálogo do ObrasGov, com linhas exatas e sem somas | Demais módulos do Transferegov, pagamentos, geometrias e reconciliação |
| Histórico e exportação | Versões, antes/depois, links, CSV/JSON/texto e seleção limitada; quatro percursos específicos | Valores de metadados não constituem pagamento |
| Observação guiada | Escola/saúde/obra, gravação privada, revisão/retirada e cópia; browser guided | Processo operacional de moderação e recurso |
| Grupos | Membros, convites, tarefas, compartilhamento explícito, revisão independente, retirada e fotos aprovadas visíveis somente a membros; browser groups | Gestão operacional, retenção e moderação de abuso; o grupo não publica a observação |
| Documento nativo | Extração, posições, tabelas, candidato e vínculo revisado; famílias lexicais de convênio/plano de trabalho/contrato/aditivo; datas e valores com papéis separados; tabelas multipágina somente com cabeçalho idêntico repetido; orientação por rotação; página híbrida e campo do trecho; sinais de privacidade/assinatura sem reter valores; PDF original privado com SHA-256 e download de revisor; prévia de página via Poppler validada em container com PDF sintético; verificação de integridade e limpeza de órfãos com dry-run; browser extended | Corpus oficial diversificado, métricas por família, retenção/expurgo dos referenciados e prévia em corpus oficial |
| OCR seletivo | Integração local; uma página sintética PT processada anteriormente; fila persistente com quotas, lease, retry, cancelamento, retenção, CLI e rotas de revisor; rotas híbrida/orientação usam elegibilidade explícita; nenhum byte/texto na fila | Avaliação com corpus oficial e operação em produção |
| Preservação OCR | Quatro originais sintéticos + dois derivados + manifesto no Git; conferência offline obrigatória | Não chamar de convênios oficiais nem usá-los como dados reais |
| Distribuição de dados | Releases v1 de saúde/recursos e educação com hashes e entrada fixada; instalação e API reverificadas em 20/10/2026 (96.123 lugares/6.679 recursos; 138.086 escolas elegíveis/76.106 excluídas); reconciliação `installed` vs `declared` em `ops/national_reconciliation.py` com gap −484 saúde e gap 0 escolas, por UF e sem denominador municipal | Renovação periódica, nova seleção de dados, denominadores por território e deploy público |
| Instalação do pacote | Um comando; staging privado; banco novo atômico; baseline Alembic 0001; 35 regressões novas | Migração de dados históricos e downgrade de produção; não sobrescreve banco ativo com usuários |
| Mapa/WebGL | Worker empacotado, mapa opcional e teste de renderização isolada | Fonte de tiles/3D externa e aparelhos limitados |
| Panoramas e fotos | Fotos privadas com upload opcional, revisão, retirada e compartilhamento em grupo; panorama não entregue | Provedor/licença/captura de panorama, política de retenção e moderação operacional |
| Idiomas e layout | pt-BR/en/es, 320/390/1440 pixels nos percursos Chromium; axe A/AA, landmarks e skip link focável | Auditoria humana, Safari e dispositivos físicos foram retirados do escopo pelo owner; não são certificação WCAG |
| Banco e container | SQLite; PostgreSQL 16 efêmero provado via Compose e stack local durável com volume, migração one-shot, backup lógico, restore em banco novo e health em `:8009`; baseline Alembic 0001 e `check` sem deriva em SQLite/PostgreSQL; worker documental 3.14.8 com Poppler/Tesseract; container não-root/read-only | Produção com TLS/PITR, backup offsite, restauração automatizada, migração de dados histórica, multi-réplica e failover |
| Dependências | Pins exatos, locks Linux (51), Windows (54) e macOS arm64 (50), certifi 2026.10.19/Pillow 13.0.0 corrigidos, instalação hash-checked | Auditoria completa, imagem/browser por digest, macOS Intel/outras arquiteturas |
| Implantação pública | Não comprovada | URL, HTTPS, dados duráveis, atualizações, backups e rollback reais |

A operação no núcleo não usa chatbot, embeddings nem chave paga de mapas.
Nomes semelhantes ou proximidade espacial não criam vínculos financeiros.
Famílias documentais são marcadores lexicais sujeitos a revisão, não uma
classificação jurídica. Unir tabelas por cabeçalho repetido não prova que o
documento ou a tabela esteja completo. Documentos PNCP coletados ficam em pasta
privada, sem rota pública e sem vínculo automático com lugar ou recurso; um
documento ausente de listagem completa é marcado `not_listed`, não como
cancelado. Sinais de privacidade e assinatura são candidatos lexicais; a
ausência de sinal não prova que o documento esteja anonimizado.
