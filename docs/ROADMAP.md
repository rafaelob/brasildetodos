<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Roadmap reconciliado — Brasil de Todos

Revisão funcional: `8324b762`. Estado de execução: `../TODO.md`.
Matriz por capacidade: `FEATURE_MATRIX.md`. Evidências: `STATUS.md`,
`reports/20260906-verified-closeout.json` (fechamento 06/09) e
`data/releases/education-2025-20260907-v1.json` (catálogo escolar posterior).
A versão anterior está preservada em `history/ROADMAP_89584b82.md`; não usar
seus bloqueios antigos como estado atual.

## Base já publicada

O núcleo funciona sem LLM: busca e fichas com proveniência; mapa progressivo;
favoritos e histórico; comparação de lugares; descoberta municipal; cobertura e
ledger de importações; observações guiadas; documentos privados com revisão;
recursos versionados, compartilhamento/exportações e grupos privados persistentes.
As interfaces estão integradas e os doze percursos Chromium são executados nos
três idiomas e larguras definidas. Isso não certifica leitores de tela ou aparelhos.

O catálogo `public-data-20260906-v1` contém 96.123 registros CNES elegíveis no
perfil adotado, com sete sem coordenadas, e 6.679 recursos: 6.677 contratos PNCP
publicados em 04/09/2026, um plano especial e um projeto Obrasgov; tabela finance
com 0 eventos. Os arquivos e hashes estão em Releases; o acervo sintético do OCR
está versionado em `tests/corpus/ocr-reviewed`. Não são um corpus oficial nem
dados de produção.

A release `education-2025-20260907-v1` é independente: 138.086 escolas públicas
declaradas ativas, todas sem coordenadas (0 geometria), com registros nas 27 UFs;
seleção `data/releases/education-2025-20260907-v1.json`. Não substitui a edição
CNES/recursos. Presença nas 27 UFs não é completude; a união dos ZIPs não é KPI
de instalação viva nem deploy público.

O lote de 06/09/2026 fecha instalação atômica de `public-data-20260906-v1` em
banco novo, proteção contra sobrescrita/arquivos auxiliares, seleção independente
dos bytes publicados, verificação contínua do corpus e repetição do aceite com
essa release. A união dos ZIPs de saúde e educação não é KPI de instalação viva.

## P0 — Dados úteis, atuais e reproduzíveis

Prioridade D01–D06 do TODO. Em 06/09/2026 o download Inep falhou com
`SSLCertVerificationError` código 20 (`reports/20260906-inep-tls-cb873ed.json`);
TLS não foi desabilitado. Em 07/09/2026 `education-2025-20260907-v1` publicou
138.086 escolas públicas ativas, 0 geometria, 27 UFs. Permanecem: transporte TLS
verificado para edições futuras; reconciliar denominadores; atualizar CNES com
competência explícita; programar revisitas/retomada e gerar edições revisadas.
Não substituir edição, fonte ou origem silenciosamente. 27 UFs não certifica
completude. `public-data-20260906-v1` continua a edição CNES/recursos.

Aceite: arquivos oficiais preservados, partições reconciliadas, registros sem geo
pesquisáveis, relatório de exclusões/quarentena, importação atômica, reexecução
idempotente e pacote novo validado antes de disponibilização. As tags
`public-data-20260906-v1` e `education-2025-20260907-v1` continuam seleções
históricas fixas, não um catálogo que se atualiza sozinho. A união dos ZIPs não
é KPI de instalação viva.

## P0 — Recursos e obras sem atribuições falsas

Prioridade F01–F05: ampliar tabelas Transferegov, Obrasgov físico/geo, PDDE/FNS e
anexos. Manter cada quantia na sua fase e fonte; destinatário administrativo não
é automaticamente beneficiário local. Cruzamentos devem ser reprodutíveis e
vínculos documentais revisados, incluindo correções/estornos/aditivos.

Aceite: esquemas e dados reais inspecionados, identidades estáveis, testes de
paginação/retomada/rollback, histórico de versões e reconciliação que impeça dupla
contagem. A janela PNCP já aceita não representa toda a história do PNCP.

## P0/P1 — Evidência documental e participação responsável

Prioridade O01–O03 e U01–U04: corpus oficial anotado; métricas por campo e
abstenção; fila operacional com quotas/cancelamento/retenção; fotos minimizadas;
panoramas opcionais; recuperação de conta e processo de moderação.

Aceite: origem e direito de reutilização revisados, dados privados fora das
exportações, autor pode retirar evidência, duas revisões conceitualmente distintas
(grupo e plataforma), exclusões conciliadas com backups e mecanismos operacionais
exercitados. Não incentivar acusação ou transformar fotografia em laudo.

## P0 — Produção e qualidade além do runner

Prioridade U05 e P01–P05: domínio/HTTPS, banco/objetos duráveis, implantação real,
monitoramento/atualização, backup/restore/rollback, carga e segurança de dependências.
A matriz adicional inclui assistive technology, Safari/iOS, Android físicos e
WebGL limitado. Python 3.14.7 e Node 24.20.0 permanecem requisitos exatos.

Aceite: URL pública, revisão comprovada, dataset instalado e manifesto exposto,
rotas privadas protegidas, restauração de dados e rollback demonstrados no ambiente
implantado. Container temporário read-only e API em TestClient são evidências de
integração, não esse aceite de produção.

## P1/P2 — Camadas complementares

P06: setores/indicadores IBGE, conectividade escolar/Giga e camadas globais úteis.
Cada fonte entra apenas com caso de uso cidadão, licença, referência temporal e
método de associação conhecido. Filtros vazios não são prova de ausência de serviço.

## Política de planejamento

Não publicar percentual global de pronto nem marcar itens nacionais por tabela
sintética. O fechamento atual não apaga nenhum requisito global. O TODO divide
implementação, dados reais e operação; novos lotes seguem essa ordem e preservam
histórico de decisões, inclusive tentativas que falharam.
