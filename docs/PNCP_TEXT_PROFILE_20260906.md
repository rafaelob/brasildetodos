<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# PNCP: diagnóstico comprovado e preservação integral do objeto

Em 2026-09-06, a execução 34044147503, revisão 506ca93f, coletou a consulta
completa de publicações de 2026-09-04: 6.677 registros em 14 páginas.
A transação foi revertida. O diagnóstico restrito identificou:

- campo: objetoContrato;
- tipo: string; comprimento integral e aparado: 5.120 caracteres;
- limite local anterior: 4.000;
- referência: 07660350000123-2-000481/2026;
- hash da página: cfc57c1f76c22c9c3a6184a7c2e6c9e6d77e9fa105e556aff887af589f0bbef1.

O valor textual não foi incluído no relatório. Origem da evidência: artefato
9992641881, SHA-256 fc9ab621822a9953506bdeb3f23b6bfb7eeded774628016795c815717926b94c.

## Decisão

A publicação real demonstra que 4.000 não é um limite compatível com esse campo.
O OpenAPI consultado expõe objetoContrato como string sem maxLength. Não se
atribui ao PNCP um limite não demonstrado. O processamento adota teto próprio
16.384 somente para títulos de contratos com perfil/source pncp_contracts.
Outros perfis, nomes de compradores e números de instrumento conservam seus
limites anteriores. Valores monetários, privacidade, assinatura, escopo e
revisão documental não são alterados.

Não truncar texto, não ignorar registro, não converter erro em sucesso. Acima do
orçamento local, manter diagnóstico estrutural e rollback. Registro bruto e
hash de origem continuam separados dos dados normalizados.

## Validação

14 regressões adicionais: 4.001/5.120 caracteres, teto/recusa, Unicode, perfis
não PNCP, demais campos, importação idempotente, histórico, exportação em três
formatos e preservação da versão anterior quando outra linha falha.
Esses casos são sintéticos e identificados como tal. A próxima execução oficial
precisa confirmar a janela inteira; esta correção não é certificação nacional.

A integração da nova API de Meus lugares foi bloqueada pela ferramenta de
publicação e permanece ausente do main; não é dependência desta correção.
