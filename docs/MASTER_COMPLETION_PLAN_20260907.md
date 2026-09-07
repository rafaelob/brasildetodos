<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Brasil de Todos — plano mestre de conclusão

Data de referência: 2026-09-07. Trabalho exclusivamente no `main`, sem force push. Este documento organiza o escopo restante; não declara a conclusão integral do produto. As evidências abaixo pertencem às revisões identificadas e não certificam automaticamente commits posteriores.

## Contrato de produto

Plataforma web open source nacional, em pt-BR/en/es, para explorar serviços e território, acompanhar obras e recursos públicos, consultar evidências e colaborar. Python 3.14.7 e Node 24.20.0. Nenhum modelo de linguagem, banco vetorial, chave de mapa paga ou serviço de e-mail é requisito do núcleo. Dados oficiais, observações, candidatos extraídos e relações confirmadas permanecem separados. Recursos previstos, contratados, transferidos e pagos não são somados entre fases. Ausência de coordenadas não exclui um serviço da busca.

## Evidências já obtidas

- [x] Catálogo de saúde/território e recursos distribuído em `public-data-20260906-v1`: 96.123 estabelecimentos elegíveis pelo perfil cadastral adotado, sete sem coordenadas e 6.679 recursos. Trata-se de recorte declarado, não disponibilidade atual de atendimento.
- [x] Catálogo escolar 2025 distribuído em `education-2025-20260907-v1`: 138.086 escolas públicas declaradas ativas, selecionadas de 214.192 linhas; todas sem coordenadas na distribuição utilizada. Não são vagas disponíveis.
- [x] Instalação unificada publicada em `e718883da8a16e69a256fc9b65cbb78361baf027`, com correção de pré-requisitos em `4310c7e735e4593946791876d34943c56c6d9d40`.
- [x] Aceite integrado `34131239400` aprovado sobre a revisão `4310c7e735e4593946791876d34943c56c6d9d40`: instalação dos dois pacotes publicados, API e interface compilada. Artefato `10022258065`, SHA-256 `7393b7cc500893cf593e74d65883ae5f37f42ff6246357874f6c8b6f8c3ea0e9`.
- [x] Pesquisa, fontes, favoritos, histórico, comparação, exportação, cobertura, descoberta municipal, observação guiada e grupos privados possuem implementações e percursos de regressão publicados. Consultar os recibos de cada revisão; testes Chromium não certificam dispositivos físicos.
- [x] Acervo `tests/corpus/ocr-reviewed/` preserva os materiais sintéticos do ensaio de OCR e seus hashes. Esse acervo não é corpus oficial nem estimativa de acurácia em documentos governamentais.
- [x] Plano de recuperação de conta publicado em `095141da1ef347d9e96a3117ecda24cf076465d7`.
- [ ] Publicar e aceitar a implementação de recuperação de conta. Os testes auxiliares preparados não equivalem a aprovação da interface na CI.
- [ ] Reconciliar `TODO.md`, `docs/STATUS.md`, `docs/ROADMAP.md` e `docs/FEATURE_MATRIX.md` com os recibos mais recentes, preservando estados históricos em `docs/history/`.

## Como uma tarefa fecha

Uma tarefa exige implementação integrada, testes comportamentais, documentação, commit no `main`, confirmação da referência remota e evidência da revisão executada. Recursos dependentes de fonte externa precisam ainda de ensaio com dados reais; recursos operacionais precisam de ensaio no ambiente implantado. Não usar porcentagem global de conclusão sem escopo e denominador definidos. Não converter testes ignorados, erros de coleta ou indisponibilidade externa em sucesso.

Cada recibo registra: ID da tarefa, revisão, ambiente e runtimes, comando, código de saída, resultado, entradas selecionadas, hashes quando aplicáveis, limitações e referência da execução. Logs públicos não contêm segredos, tokens de recuperação, dados de contas ou documentos privados.

## Lote A — fechar recuperação de conta e integração atual

Dependência: instalação unificada publicada. Aproveitar o código já preparado, sem reimplementar contratos paralelos.

- [ ] A01 Revisar a implementação existente de recuperação e integrar rotas à aplicação, mantendo autenticação, CSRF e limites por tentativa.
- [ ] A02 Emitir segredo de recuperação somente após reautenticação; exibi-lo uma única vez e armazenar apenas digest apropriado. Não incluir segredo em URL, telemetria, exportação geral ou logs.
- [ ] A03 Permitir rotação e revogação; códigos anteriores deixam de funcionar. Documentar validade e impossibilidade de recuperação sem senha nem código previamente guardado.
- [ ] A04 Consumir o código e atualizar a senha numa única transação; revogar sessões anteriores, impedir reutilização concorrente e manter rollback em falhas. Conta desativada não é reativada por esse fluxo.
- [ ] A05 Integrar interface acessível nos três idiomas: geração, confirmação de guarda, rotação, recuperação, erros genéricos e cancelamento. Limpar o segredo ao sair da tela ou encerrar sessão.
- [ ] A06 Testar duas sessões reais de navegador, recarga, código usado/expirado/revogado, senha antiga recusada e acesso com senha nova. Manter todos os percursos já existentes.
- [ ] A07 Aprovar CI exata e atualizar os checks com SHA e execução. Não atribuir à recuperação de conta a conclusão das demais funções de moderação.

## Lote B — dados nacionais atualizáveis

- [ ] B01 Reconciliar as contagens escolares por UF e município com o universo efetivamente processado e o perfil de elegibilidade. Separar total da fonte, excluídos, inválidos e publicados.
- [ ] B02 Registrar versão do dicionário, referência temporal e recibo do arquivo bruto escolar. Publicar somente materiais autorizados e minimizados; não adicionar microdados individuais por conveniência.
- [ ] B03 Selecionar e validar nova competência CNES; medir diferenças e alterações de esquema antes da publicação.
- [ ] B04 Criar agenda de atualização por fonte com janela sobreposta, revisitas, retomada e estado de tentativa independente do último snapshot válido.
- [ ] B05 Aplicar carga preparada de forma transacional ao banco operacional sem substituir contas, sessões, grupos ou observações. Testar rollback, interrupção e preservação de vínculos.
- [ ] B06 Publicar indicadores de atualidade, cobertura e falhas sem inferir encerramento de serviço pela ausência numa coleta.
- [ ] B07 Distribuir nova edição por tag e seleção independente; não sobrescrever silenciosamente releases existentes.

## Lote C — instrumentos, obras e execução financeira

- [ ] C01 Transferegov: ingestão de propostas e instrumentos com identidade separada, assinatura, modalidade, objeto, vigência, concedente, beneficiário e escopo territorial.
- [ ] C02 Transferegov: metas, etapas, cronogramas, aditivos e prorrogações com fonte e referência por evento.
- [ ] C03 Transferegov: empenhos, desembolsos, pagamentos, contrapartidas, devoluções e estornos com fase, perspectiva e destinatário explícitos.
- [ ] C04 Obrasgov: execução física e geometrias vinculadas pela identidade do projeto; preservar data e método. Endereço do comprador não é localização da obra.
- [ ] C05 PNCP: revisitar contratos conhecidos, alterações e anexos; preservação de precisão monetária e textos completos. Consulta temática não representa censo de todos os contratos.
- [ ] C06 FNDE/PDDE e FNS: verificar primeiro acesso, identificadores e granularidade; publicar dados no nível da escola, unidade executora, fundo, rede ou município que a fonte realmente sustenta.
- [ ] C07 Reconciliar representações duplicadas de um mesmo evento entre fontes; tratar correções e cancelamentos. Não resolver divergências por soma, média ou último escritor silencioso.
- [ ] C08 Expor na interface vínculos diretos, revisados e territoriais, com linhas do tempo e fontes. Candidatos não confirmados não compõem totais públicos.
- [ ] C09 Validar em corpus real selecionado com denominador e amostra documentados; testar casos de muitos contratos para várias unidades e ausência de alocação por unidade.

## Lote D — documentos oficiais e processamento operacional

- [ ] D01 Inventariar documentos realmente baixados e processados; distinguir consulta pelo navegador de obtenção dos bytes. Registrar origem, hash, páginas, licença e revisão de privacidade.
- [ ] D02 Selecionar corpus oficial revisado e anotado por campo, com famílias distintas: instrumento, plano de trabalho, aditivo, edital, contrato, medição e prestação de contas.
- [ ] D03 Extração nativa por página; OCR seletivo apenas em páginas sem texto útil, preservando originais, assinatura e localização do trecho. Separar texto nativo, OCR e interpretação.
- [ ] D04 Tratar tabelas multipágina, cabeçalhos repetidos, quantidades/unidades, subtotais e mudanças de período. Não escolher automaticamente o maior valor monetário.
- [ ] D05 Medir precisão, cobertura, falsos vínculos e abstenção por campo/família; não reportar acurácia oficial usando somente fixtures sintéticas.
- [ ] D06 Fila persistente com quotas por documento e operador, timeout, memória, cancelamento, reexecução idempotente, isolamento sem credenciais e recuperação de tarefas interrompidas.
- [ ] D07 Retenção, expurgo e trilha de auditoria dos originais/derivados, inclusive exclusão de contribuições e backups; não publicar textos privados por serem tecnicamente extraíveis.
- [ ] D08 Revisão com documento/trecho e candidato lado a lado; confirmação da transcrição distinta da confirmação do vínculo. Nenhuma publicação automática de OCR.

## Lote E — fotografias, panoramas e colaboração

- [ ] E01 Envio de imagem com validação real do formato, limites, normalização e remoção de metadados; armazenamento privado e nomes não controlados pelo usuário.
- [ ] E02 Revisão e redação de dados pessoais antes da publicação; remoção pelo autor, exclusão e propagação para derivados/cache/backups conforme política documentada.
- [ ] E03 Fonte, autor autorizado, licença, data de captura e modo de observação visíveis. Imagem histórica ou panorama não implica presença física nem funcionamento atual.
- [ ] E04 Integrações opcionais Panoramax/Mapillary com erro, falta de cobertura e restrições de licença explícitos. Nenhum bloqueio ao mapa/lista ou contribuição textual.
- [ ] E05 Recursos de moderação: contestação, revisão independente, registro de decisão, prevenção de abuso e privacidade de denunciantes; não transformar relatos em acusações automáticas.
- [ ] E06 Grupos: verificar retenção, retirada de evidência, arquivamento, transferência e saída em todos os fluxos, inclusive após recuperação/desativação de conta.
- [ ] E07 Notificações ou colaboração síncrona somente com consentimento, cancelamento e operação sustentável; presença virtual não publica localização física.

## Lote F — mapas, 3D, design e acessibilidade

- [ ] F01 Validar basemap externo, worker, tiles, atribuições, erros de rede e recuperação; registrar fonte e data da camada.
- [ ] F02 Edificações e relevo em 3D somente onde houver dados compatíveis e licenciados; marcar alturas aproximadas. Não apresentar volume genérico como levantamento exato.
- [ ] F03 Validar navegadores sem WebGL, dispositivos de memória limitada, movimento reduzido e economia de dados. Lista e busca permanecem completas.
- [ ] F04 Revisar arquitetura da informação e todas as telas: explorar, ficha, meus lugares, minha região, recursos, documentos, grupos, conta, revisão e cobertura.
- [ ] F05 Conferir estados vazios, carregamento, erro, atualização, cancelamento e respostas atrasadas; nenhum botão de funcionalidade inexistente sem estado explícito.
- [ ] F06 Auditar pt-BR/en/es, unidades, datas, pluralização, nomes acessíveis, foco, teclado, contraste, zoom e reflow. Não transformar checklist automático em certificação WCAG completa.
- [ ] F07 Executar leitores de tela e Safari/iOS/Android físicos; registrar dispositivos e resultados reais separadamente dos testes Chromium emulado.
- [ ] F08 Camadas IBGE detalhadas, conectividade e fontes mundiais: caso de uso, período, licença e relação territorial revisados; população residente não é fila de espera.

## Lote G — operação pública e segurança

- [ ] G01 Inventariar destino de implantação e permissões realmente disponíveis; não criar custos ou publicar dados pessoais sem configuração revisada.
- [ ] G02 Implantar frontend/API com HTTPS, banco e documentos duráveis, menor privilégio e identificação da revisão servida; publicar URL somente depois de verificar resposta real.
- [ ] G03 Exercitar atualização dos dados no ambiente implantado, sem perda de contas ou conteúdo comunitário.
- [ ] G04 Backup e restauração verificados, incluindo exclusões, documentos, sessões revogadas e consistência entre objetos e banco.
- [ ] G05 Rollback por revisão e dados, monitoramento, alertas, limites de consumo e procedimento de incidente ensaiados.
- [ ] G06 Medir concorrência e latência sobre o catálogo combinado real; registrar máquina, carga, índices e limites. Smoke test não é prova de capacidade.
- [ ] G07 Auditar dependências Python/npm, licenças, imagens e pacotes de sistema; fixar digests e registrar exceções com prazo e renovação.
- [ ] G08 Revisar auth/CSRF, CSP, validação de upload, destinos de coleta, isolamento de parser, rate limits e recuperação. Não enfraquecer controles para passar testes.
- [ ] G09 Validar instalação Windows/macOS e arquiteturas adicionais; o lock Linux não é apresentado como universal.

## Ordem e paralelismo

1. Fechar A e consolidar os recibos da instalação unificada; publicar correções pequenas com confirmação do `main`.
2. Executar B e C em frentes separadas de D, com contratos de dados explícitos e nenhum vínculo inventado.
3. Implementar E e F preservando os fluxos existentes; validar cada componente com testes de permissão, privacidade e navegador.
4. Preparar G em paralelo, mas sua conclusão exige ambiente real. Nenhum checklist de infraestrutura substitui deploy observado.
5. Ao fim de cada lote, atualizar TODO e matriz com evidências por tarefa, registrar pendências reais e confirmar todos os commits remotos.

## Critério de conclusão do escopo

A conclusão integral exige todos os requisitos aplicáveis acima implementados e aceitos, ou uma alteração explícita de escopo aprovada pelo responsável. Indisponibilidade de fornecedor, licença não esclarecida, ausência de hardware físico ou falta de configuração de produção são bloqueios registrados, não funcionalidades concluídas. Material de teste sintético permanece segregado dos dados oferecidos ao cidadão. A publicação deste plano, por si só, não altera o estado de implementação das tarefas.
