<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Lote: Minha região, coletas oficiais e entrega verificável

Base inspecionada: bca24a3cf5af0196921cae2134c2bf2a795dc97f.
Python 3.14.7 / Node 24.20.0. Somente main, sem force push.
Não reimplementar favoritos, comparação, guias de visita, exportações, instalação
transacional de recursos ou precisão monetária que já chegaram ao repositório.
As versões anteriores locais são insumos para comparação, nunca substituem main.

## Plano e critérios de aceite

- [x] P01 — Ler main, AGENTS, TODO e comparar a implementação e evidências remotas.
- [x] P02 — Registrar este plano antes da alteração do produto.
- [ ] P03 — Completar Minha região: descoberta municipal paginada, resumo de
  serviços carregados e recursos com escopos territoriais explicitamente separados.
- [ ] P04 — Integrar a jornada nacional na navegação com estados independentes,
  pesquisa, teclado, carregamento, erro/retentativa, filtros e três idiomas.
- [ ] P05 — Criar testes de API, consulta consistente, limites, projeção pública,
  município sem dados, registros sem coordenadas e prevenção de falsa atribuição.
- [ ] P06 — Aprovar build e jornada nativa de navegador nos runtimes exatos;
  preservar todos os testes existentes e conferir 320/390/1440 pixels.
- [ ] P07 — Diagnosticar e melhorar a coleta oficial escolar sem relaxar identidade,
  origem, ano, privacidade ou regras de publicação; executar a tentativa e registrar
  o resultado efetivo, incluindo falhas externas.
- [ ] P08 — Validar a nova jornada com dados governamentais coletados/reutilizados,
  distinguindo nova coleta de replay e hashes de bytes de autenticação da fonte.
- [ ] P09 — Fechar um caminho operacional de atualização com orçamento, exclusão
  mútua, checkpoint e falha visível; publicação apenas de arquivos validados.
- [ ] P10 — Executar suíte completa, revisar frontend/backend e atualizar TODO,
  ROADMAP/STATUS com evidências da revisão final, sem marcar código não integrado.
- [ ] P11 — Commit e atualização de main pelo conector, preservar concorrência e
  confirmar SHA remoto e conclusão da CI correspondente.

## Auditoria das frentes completas

Catálogo escolar nacional e denominadores; atualização CNES; IBGE/território;
recursos PNCP e demais módulos Transferegov/Obrasgov; financeiro/FNS/PDDE;
documentos, anexos/OCR e revisão; mapa/3D/panoramas; serviços/favoritos/comparação;
visitas, grupos/tarefas/fotos; autenticação, recuperação, retenção/moderação;
acessibilidade e dispositivos; instalação/publicação de catálogos, agendamento,
backup/restauração, observabilidade, licenças e implantação pública.
Cada frente deve constar no TODO, com critérios de término e bloqueios específicos.
Ausência de dado não é inexistência de serviço. Instalação de teste não é deploy.
Não haverá mocks ou valores de demonstração no caminho de produção. Fixtures
isoladas continuam necessárias para reproduzir erros e verificar comportamento.

## Evidência inicial

O último ensaio escolar 34048537320, tentativa 2, descobriu na página oficial
https://download.inep.gov.br/dados_abertos/microdados_censo_escolar_2025_.zip e
terminou em ConnectTimeout antes do download. Não é falha de interpretação do CSV.
A contagem e as permissões de cada fonte serão verificadas; não há autorização
para contornar restrições de acesso ou substituir silenciosamente a edição.
