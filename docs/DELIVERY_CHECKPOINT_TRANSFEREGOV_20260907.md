<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Checkpoint verificável — processamento de imagens e contratos Transferegov

Data de referência: 2026-09-07. Este registro consolida resultados observados; não certifica a conclusão integral do produto nem uma implantação pública.

## Publicações observadas no main

| Revisão | Entrega | Limite |
|---|---|---|
| dcc3b0a6c0872338e0d48f4c73dc889e31920fe1 | Plano de entrega de fotografias e reconciliação do backlog | Planejamento não equivale a feature implantada. |
| db36fdc2d79662aa02a0058ec4de5fcf3129fa42 | Processamento independente JPEG/PNG, máscaras opacas, remoção de metadados e CLI sem sobrescrita | A integração de upload pela API não foi publicada; não apresentar o processador como fluxo web concluído. |
| abfe422a51a564e0c845a0b8d47964d9ec0003b4 | Inspeção limitada dos contratos públicos de publicação do Transferegov | Inspeção de esquema não importa instrumentos nem eventos financeiros. |
| d62105e604c939e534e7b5775e50023c4ad47a23 | Inspeção do índice CSV indicado pelo publicador | A primeira tentativa não encontrou os nomes esperados. |
| 4385ae8d39dac38ed72a790f4aca7329851da878 | Tratamento de namespaces e registro dos nomes efetivamente publicados | A tentativa ainda usava nomes antigos; a falha deve permanecer no histórico. |
| c6373602b839c3146d48b1d475d0dcf028e5e320 | Uso dos nomes atuais siconv_convenio.zip, siconv_termo_aditivo.zip e siconv_desembolso.zip | Validação de amostras/cabeçalhos não substitui leitura e reconciliação integrais. |

## Evidências já observadas

- Quality 34148311903: backend, build web e treze jornadas existentes aprovados para db36fdc2.
- Descoberta de contratos de publicação 34148764480: concluída; artefato 10028609137.
- Inspeções CSV 34149098763 e 34149352318: falharam antes da confirmação do contrato de nomes. Não foram cargas publicadas.
- Inspeção CSV 34149747654: concluída para c6373602; artefato 10028933214, 2.810 bytes, SHA-256 03b0fe1ef02ab86be1b4418bedf13bc6211b3f6ede5458bf6a64103a8c588365.
- Runtime integration 34149747683: concluída para c6373602.
- Quality 34149747794: resultado final não confirmado neste checkpoint. Não herdar aprovação de outra revisão.

## Fechamento pendente da integração financeira

- [ ] Congelar os três arquivos completos e recibos, validar bytes, entradas ZIP, encoding completo, cabeçalhos, limites e contagem de linhas.
- [ ] Implementar contratos de normalização por tabela com identificadores originais, datas tipadas e valores decimais exatos.
- [ ] Distinguir pré-convênio e instrumento assinado por campos publicados; não deduzir assinatura de valores ou situação textual isolada.
- [ ] Preservar aditivos negativos como alterações declaradas com papel identificado; não tratá-los como pagamento, estorno ou novo valor global sem evidência.
- [ ] Manter desembolsos separados de compromissos, saldos acumulados e pagamentos a fornecedores; validar a granularidade de cada registro.
- [ ] Reconciliar referências por identificadores; separar órfãos, duplicidades e conflitos sem associar escolas ou UBS por proximidade ou nome.
- [ ] Excluir campos bancários e dados pessoais desnecessários das projeções públicas, relatórios e artefatos.
- [ ] Persistir versões e atualizar conjuntos transacionalmente, preservando a última carga válida quando houver falha.
- [ ] Integrar a apresentação com os três idiomas e distinguir valor previsto, alteração e desembolso; impedir totais entre fases incompatíveis.
- [ ] Testar entradas inválidas, duplicidades, alterações, rollback, exclusões indevidas, precisão, fontes e limites.
- [ ] Executar o aceite sobre dados oficiais identificados em Python 3.14.7 e o frontend compilado em Node 24.20.0.
- [ ] Confirmar os commits no main, a CI da mesma revisão e atualizar TODO/ROADMAP/STATUS e as issues correspondentes.

## Freeze 2026-09-09

Validação dos ZIP cacheados em `data/downloads/transferegov/` contra `receipts.json` (bytes, SHA-256, membro ZIP e colunas obrigatórias do CSV). Contagens de assinados vs pré-convênio, aditivos negativos e instrumentos órfãos por passagem completa de cabeçalho/contador (sem persistir linhas); importação integral não executada (`records_imported: 0`). Relatório `docs/reports/20260909-transferegov-freeze.json`: `financial_total_computed: false`, `national_catalog_certified: false`, `public_data_v1_unchanged: true`. Ingestão de operador exige `--database` em SQLite novo e recusa `data/bdt.db`. Este freeze não republica B07 e não marca os itens pendentes acima como concluídos.

## Demais bloqueios que este lote não resolve

Upload web de fotografias e recuperação de conta permanecem sem publicação confirmada da integração central da API. A escrita anterior foi bloqueada pela verificação de segurança da plataforma, não por uma alegação de GitHub somente leitura. O componente independente de preparação de imagens não encerra esses fluxos.

Permanecem distintos: demais módulos Transferegov, execução física/geometrias Obrasgov, PDDE/FNS, reconciliação entre fontes, atualização contínua de cadastros, corpus oficial de OCR anotado e revisado, operação da fila documental, panoramas e mapas externos, acessibilidade assistiva/dispositivos físicos e implantação pública com persistência, backups, restauração e monitoramento.

Não há novo resultado de coleta, teste, deploy ou aprovação implícita neste documento. Fechar cada requisito exige evidência específica da revisão e do ambiente correspondentes.
