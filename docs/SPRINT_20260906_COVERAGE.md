<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Plano de execução: cobertura compreensível e importações públicas

Base conferida: `33a044276220b83819e87b3d76e7a43176ea7a25`.
Trabalho apenas no main, preservando atualizações concorrentes. Este incremento
fecha uma jornada de cidadão completa (API → interface → teste de navegador),
sem substituir a ingestão nacional, a reconciliação financeira ou o deploy.

## Decisão de prioridade

O main já contém precisão subcentavo, resposta PNCP 204 e compartilhamento/exportação.
A CI Quality 34036732635 está aprovada. Esses avanços são preservados, não refeitos.
O problema textual PNCP continua pendente e não será contornado nesta entrega.
A prioridade é R03 do TODO: explicar o que esta instalação realmente carregou,
separando disponibilidade cadastral, geometrias e resultado de importações.

## TODO desta entrega

- [x] U01 — Ler o main, AGENTS, TODO e plano e obter o snapshot exato.
- [x] U02 — Registrar o plano antes da implementação.
- [ ] U03 — API pública de cobertura e histórico paginado de importações, com
  projeção explícita de campos e sem dados de usuários, caminhos locais, consultas
  internas, erros livres ou referências privadas.
- [ ] U04 — Preservar métricas de registros carregados mesmo após importação falha;
  distinguir contagens tentadas de publicadas, parcialidade e ausência de histórico.
- [ ] U05 — Frontend responsivo com indicadores compreensíveis, fonte/UF/status,
  datas, paginação, estado vazio, falha e tentar novamente nos três idiomas.
- [ ] U06 — Testes comportamentais de API, projeção, contagens, filtros e tradução.
- [ ] U07 — Build e navegador com API real, estados de erro/recuperação e leitura
  em 320, 390 e 1440 pixels. Dados sintéticos identificados somente nos testes.
- [ ] U08 — Atualizar TODO, ROADMAP e STATUS com checks sustentados por evidência;
  manter pendências de dados nacionais, frontend/mapa/3D, backend e operação.
- [ ] U09 — Publicar commits no main sem force push e conferir CI e referências.

## Critérios de aceite

Uma pessoa deve distinguir “há registros nesta instalação” de “a fonte está completa
ou atualizada”. Nenhum indicador de cobertura é um atestado de atendimento.
Importação com falha não significa ausência do serviço; sucesso em um arquivo
não certifica o país. A data da tentativa não substitui a referência do dado.
Consultas públicas não retornam fonte bruta, traceback, arquivo, token ou usuário.
Nenhum novo provedor de IA, mapa ou geocodificação é necessário ao fluxo.
