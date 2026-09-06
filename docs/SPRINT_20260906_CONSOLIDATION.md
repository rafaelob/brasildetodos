<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Próximo lote: integração, dados reais e validação ponta a ponta

Data: 2026-09-06. Base inicialmente inspecionada: `25f55e0302cca4ea516076235253eb0c6b6eb54f`.
Trabalhar exclusivamente no main; reler a referência antes de cada publicação;
nunca sobrescrever mudanças concorrentes nem usar force push.
Python 3.14.7 e Node 24.20.0 permanecem os runtimes exigidos.

## Diagnóstico e ordem do lote

A base contém locks verificados e o novo mapa progressivo. Quality 34042814576
falhou no teste de mapa: um seletor por label encontra a região e o campo de
busca. Não é evidência de falha de todo o renderizador nem de aprovação do mapa.
Os pacotes locais de runtimes e Meus lugares precisam de revisão diferencial,
não aplicação cega. Coleta oficial, implementação, suíte e deploy são entregas
separadas. Nenhum resultado anterior será apresentado como novo.

## Checklist deste lote

- [x] B01 — Ler main, AGENTS, TODO, resultados de CI e obter snapshot exato.
- [x] B02 — Registrar plano antes de alterar o produto.
- [ ] B03 — Reproduzir/corrigir a falha do percurso de mapa, preservando interação
  WebGL, seleção, filtros, 3D, recuperação, lista alternativa e três idiomas.
- [ ] B04 — Reconciliar o incremento de runtimes: OCR, encerramento de recursos,
  cancelamento de operações web e dados atrasados; preservar locks publicados.
- [ ] B05 — Reconciliar Meus lugares: API limitada, versões e diferenças públicas,
  favoritos somente no dispositivo, estados ausentes/fora do perfil e i18n.
- [ ] B06 — Executar testes comportamentais de backend e helpers; manter piso de
  cobertura e controles de autenticação, privacidade e valores exatos.
- [ ] B07 — Compilar e testar a interface nos runtimes exatos, com navegação,
  teclado, erros/recuperação e 320/390/1440 pixels; guardar evidências reais.
- [ ] B08 — Identificar o campo que bloqueia PNCP mediante diagnóstico limitado
  a identidade/campo/tipo/escala/comprimento, sem publicar payload pessoal.
- [ ] B09 — Resolver o contrato observado quando comprovado, com regressão;
  preservar original, limites, rollback e ausência de truncamento silencioso.
- [ ] B10 — Reexecutar coleta/importação oficial delimitada e registrar contagem,
  proveniência, estado final e consulta pela API, sem certificar o país por amostra.
- [ ] B11 — Reavaliar acesso à edição nacional escolar e registrar falha ou carga
  reconciliada, sem trocar edição nem geocodificar silenciosamente.
- [ ] B12 — Conferir dados reais sobre os novos endpoints e registrar alcance.
- [ ] B13 — Atualizar TODO, ROADMAP, STATUS e evidências; revisar todos os itens
  pendentes por camada, inclusive trabalho bloqueado externamente.
- [ ] B14 — Publicar os commits no main e confirmar a referência e a CI da revisão.

## Visão completa do trabalho restante

### Catálogos e integração
- [ ] Educação 2025 nacional: download oficial, hash, tabelas escolares, partições,
  denominadores, rejeições e publicação atômica; não inventar coordenadas.
- [ ] Saúde: atualizações por competência, auditoria do perfil elegível e cobertura
  reconciliada; cadastro não certifica atendimento atual.
- [ ] PNCP: importação oficial reconciliada, atualização por janelas e anexos.
- [ ] Transferegov: instrumentos assinados, metas/etapas, aditivos, desembolsos,
  pagamentos e integração modular segundo os recursos realmente disponíveis.
- [ ] Obrasgov: execução física e geometrias, separadas do endereço comprador.
- [ ] PDDE/FNS e contexto IBGE/Siconfi: fontes/licenças, granularidade e datas.
- [ ] Reconciliar duplicidades, estornos e fases financeiras entre sistemas;
  impedir associação por nome/proximidade e soma indevida de etapas.

### Documentos e colaboração
- [ ] Corpus oficial para avaliar texto nativo/OCR por campo; tabelas multipágina,
  assinaturas, abstenção, versões de extratores e revisão independente.
- [ ] Fila documental com quotas/cancelamento/retomada/expurgo e original intacto.
- [ ] Grupos e tarefas coletivas com permissões, histórico e responsáveis.
- [ ] Fotos apenas com minimização, retirada, revisão e retenção demonstráveis.
- [ ] Recuperação de conta, recursos de moderação e política operacional.

### Frontend, design e território
- [ ] Meus lugares completo e validado: busca, favoritos, mudanças, fontes e ações.
- [ ] Cobertura compreensível ligada à API, sem confundir carga e fatos atuais.
- [ ] Mapa/3D com worker empacotado, origem de alturas, fallback e aceitação externa.
- [ ] Panoramas opcionais com data/licença; imagens históricas não são visitas.
- [ ] Acessibilidade assistiva, Safari e dispositivos físicos, desempenho nacional.
- [ ] Consistência visual e de linguagem em português, inglês e espanhol.

### Testes e operação
- [ ] Regressões integrais nos runtimes exigidos; nenhuma queda dos gates.
- [ ] Lockfiles verificados e auditoria de dependências com triagem documentada.
- [ ] Jobs periódicos e alertas de falha, retomada e versão anterior preservada.
- [ ] Implantação com HTTPS, armazenamento durável, responsáveis e orçamento.
- [ ] Backup/restauração/rollback em ambiente implantado, não apenas temporário.
- [ ] Revisão de licenças/fontes e dados pessoais antes da publicação pública.

## Critérios de aceite

Um check exige evidência específica. Teste sintético não é coleta real; job
concluído não é deploy; presença em 27 UFs não é completude. A interface nunca
apresenta capacidade prevista como vaga disponível, cadastro como funcionamento
confirmado ou dinheiro municipal como recurso de uma unidade sem vínculo.
A aplicação continua sem LLM obrigatório. Não publicar dados privados, segredos,
original pessoal ou logs brutos na documentação/artefatos públicos.
