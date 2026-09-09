<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Matriz de capacidades e limites verificáveis

Referência de código: `8324b762`; execuções e hashes em
`reports/20260906-verified-closeout.json`. Catálogo escolar posterior:
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
| Cobertura e importações | Painel e histórico paginado integrados | Denominadores oficiais reconciliados para certificação nacional |
| CNES | Pacote com 96.123 elegíveis, sete sem coordenadas, consulta aceita | Nova competência e validação do perfil/denominadores |
| Educação | Leitor nacional e validações; `education-2025-20260907-v1` com 138.086 escolas públicas ativas, 0 geometria, 27 UFs; seleção `data/releases/education-2025-20260907-v1.json` | Incidente Inep 06/09/2026: `SSLCertVerificationError` código 20 (`reports/20260906-inep-tls-cb873ed.json`); TLS não desabilitado. 27 UFs não é completude; denominadores abertos |
| Recursos PNCP | Janela de 6.677 contratos importada; precisão e objetos preservados | Histórico nacional completo, atualização recorrente e reconciliação |
| Transferegov/Obrasgov | Perfis de plano especial e projeto; um registro real de cada aceito | Demais módulos, pagamentos, execução física e geometrias |
| Histórico e exportação | Versões, antes/depois, links, CSV/JSON/texto e seleção limitada; quatro percursos específicos | Valores de metadados não constituem pagamento |
| Observação guiada | Escola/saúde/obra, gravação privada, revisão/retirada e cópia; browser guided | Processo operacional de moderação e recurso |
| Grupos | Membros, convites, tarefas, compartilhamento explícito, revisão independente e retirada; browser groups | Fotos, recuperação de conta e gestão operacional não são resolvidas pelo grupo |
| Documento nativo | Extração, posições, tabelas, candidato e vínculo revisado; browser extended | Corpus oficial diversificado e métricas por família |
| OCR seletivo | Integração local; uma página sintética PT processada anteriormente | Avaliação oficial, fila operacional e políticas de retenção |
| Preservação OCR | Quatro originais sintéticos + dois derivados + manifesto no Git; conferência offline obrigatória | Não chamar de convênios oficiais nem usá-los como dados reais |
| Distribuição de dados | Release v1 com hashes e entrada fixada; aceite real repetido | Renovação periódica e nova seleção de dados |
| Instalação do pacote | Um comando; staging privado; banco novo atômico; 35 regressões novas | Não migra nem sobrescreve banco ativo com usuários |
| Mapa/WebGL | Worker empacotado, mapa opcional e teste de renderização isolada | Fonte de tiles/3D externa e aparelhos limitados |
| Panoramas e fotos | Não entregues como funcionalidade de produção | Provedor/licença/captura, minimização, upload e moderação |
| Idiomas e layout | pt-BR/en/es, 320/390/1440 pixels nos percursos Chromium | Revisão assistiva/Safari/aparelhos físicos |
| Banco e container | SQLite e ensaio PostgreSQL; container não-root/read-only e frontend servido | Infraestrutura durável em produção |
| Dependências | Pins exatos, locks usados na CI | Auditoria completa, imagem/browser por digest, Windows/macOS |
| Implantação pública | Não comprovada | URL, HTTPS, dados duráveis, atualizações, backups e rollback reais |

A operação no núcleo não usa chatbot, embeddings nem chave paga de mapas.
Nomes semelhantes ou proximidade espacial não criam vínculos financeiros.
