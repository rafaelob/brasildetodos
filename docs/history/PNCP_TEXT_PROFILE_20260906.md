<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# PNCP: diagnóstico comprovado e preservação integral do objeto

## Objeto longo

Em 2026-09-06, a execução 34044147503, revisão 506ca93f, coletou a consulta
completa de publicações de 2026-09-04: 6.677 registros em 14 páginas.
A transação foi revertida. O diagnóstico restrito identificou:

- campo: objetoContrato;
- tipo: string; comprimento integral e aparado: 5.120 caracteres;
- limite local anterior: 4.000;
- referência: 07660350000123-2-000481/2026;
- hash da página: cfc57c1f76c22c9c3a6184a7c2e6c9e6d77e9fa105e556aff887af589f0bbef1.

O valor textual não foi incluído no relatório. Origem: artefato 9992641881,
SHA-256 fc9ab621822a9953506bdeb3f23b6bfb7eeded774628016795c815717926b94c.

## Preflight de todas as linhas

A execução 34045679525, revisão 21b25ba9, verificou todas as 6.677 linhas e
identificou somente uma incompatibilidade restante: título de quatro caracteres
contra mínimo local de cinco. Não houve publicação parcial de contratos.

- referência: 00394544000185-2-009902/2026;
- regra: string_too_short; comprimento 4; mínimo anterior 5;
- página: 67200b04172b2fbab680a1212ef7bb25d0fbe64042454462f02ea609c4f2168f;
- artefato 9993085431, SHA-256 e47ea2203b193c9a3cbaeaaaecd248e6466bd32f12d002e1ae8b432034c1b911.

O texto não foi reproduzido no diagnóstico. Um título curto pode ser pouco
informativo, mas isso não justifica inventar palavras ou omitir a contratação.

## Decisão

A publicação real demonstra que a faixa 5–4.000 não descreve esse campo.
O OpenAPI consultado expõe objetoContrato como string sem maxLength. O orçamento
local é 1–16.384 caracteres não vazios somente para contratos com perfil e fonte
pncp_contracts. Isso NÃO é um limite declarado pelo PNCP. Os demais perfis
conservam 5–4.000, e nomes/números conservam seus limites específicos.

Não truncar texto, não sintetizar um título substituto, não ignorar a linha.
Descrições muito curtas ganham aviso na interface; longas possuem prévia visual
e texto integral acessível por teclado. API, histórico e exportação preservam
as palavras publicadas. Valores, controles de acesso e atribuições não mudam.
Acima do orçamento, manter diagnóstico estrutural e rollback.

## Validação

Regressões para 4.001/5.120 caracteres, teto/recusa, Unicode, perfis não PNCP,
demais campos, importação idempotente, histórico e exportação. Também 13 casos
de objetos curtos, vazios/nulos e manutenção do mínimo dos outros perfis.
O preflight continua contabilizando todos os erros sem gravar; o teste de erro
de modelo mantém a verificação de constraints sem reter input ou contexto livre.

Fixtures sintéticas são explicitamente separadas das execuções reais. A próxima
execução deve confirmar a janela inteira. Nem essa janela representa toda a
história do PNCP, nem importar significa publicar uma instância de produção.

A integração da nova API de Meus lugares foi bloqueada pela ferramenta de
publicação e permanece ausente do main; não é dependência desta correção.
