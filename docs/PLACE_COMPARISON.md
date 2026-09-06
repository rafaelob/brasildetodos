<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Comparar lugares salvos

Meus lugares permite selecionar dois ou três estabelecimentos e comparar os dados
cadastrais em cartões alinhados no desktop e empilhados no celular. O foco vai para
o título ao abrir, e os controles funcionam pelo teclado. A seleção de comparação
é temporária na memória da tela; não altera favoritos nem cria registros no servidor.

Usa o endpoint de leitura em lote existente `/api/saved-places/summary`, com uma
versão por lugar. Exibe nome, tipo, endereço, telefone, serviços declarados,
município, fonte, referência e data de coleta. Não calcula ranking, probabilidade
de vaga, qualidade, distância ou disponibilidade de atendimento. Tipos e períodos
diferentes têm avisos explícitos. Ausência de campo não é ausência do serviço.

Mantém ordem e identidade entre seleção e resposta. Dado ausente, perfil alterado
e falha não recebem valores inventados. A requisição de comparação é independente
da lista; falha permite repetir sem ocultar os favoritos. Mudanças de seleção e
saída da tela abortam leituras antigas e descartam respostas atrasadas.

Nenhuma nova rota, permissão, geocodificador, chave de mapa ou modelo é necessário.
A comparação é uma apresentação dos dados públicos, não uma alteração cadastral.

## Validação

- `web/tests/place-comparison.test.mjs`: limites, identidade, estados, traduções,
  tipos, ordem, falta de dados e seleção removida.
- `backend/tests/test_comparison_route.py`: aplicação real, rota única, sem
  registro de router de teste, sem gravação de contas ou observações; fases de
  referência e itens sem coordenadas preservados.
- `ops/browser_place_comparison.py`: API real e build compilado, três idiomas,
  320/390/1440 px, seleção, limite, foco, períodos, falha e recuperação. Fixtures
  sintéticas somente no banco temporário do teste; não alimentam produção.

A execução e o SHA validado são registrados no relatório do lote; o simples fato
 de o teste existir não significa que passou.
