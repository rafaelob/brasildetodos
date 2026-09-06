<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Estado verificável — 06/09/2026

## Evidências consolidadas anteriores

A implementação inicial foi integrada ao `main`. Não há trabalho novo em branches.
A referência detalhada é `MAIN_IMPLEMENTATION_20260906.md`: catálogo CNES real com
96.123 estabelecimentos elegíveis, sete sem coordenadas, 27 UFs; 5.571 registros
territoriais preservados; OCR seletivo integrado; revisão documental e privacidade.

A revisão `2131efbf222460b6c2a6b216a59b593f114a31c7` teve Quality aprovada em
`34008771216` e catálogo real aprovado pela API em `34008771230`. OCR sintético em
português: `34008123457`. Container/PostgreSQL: `34008376130`.

## Continuidade atual: metadados públicos versionados

Implementação: perfis PNCP/Especiais/Obrasgov, coleta delimitada, versões imutáveis,
API de histórico, busca por fonte/UF/texto, interface nos três idiomas, centavos
exatos e ausência explícita de pagamentos/links automáticos.

Inspeção de schemas e amostra oficial: `34009291326`, artefato `9981954097`.
A amostra PNCP declarou 6.677 contratos em 04/09/2026; isso ainda não comprova
importação de todos eles. O workflow de intake produz seu próprio resultado.

Teste local: **446 Python aprovados**, cobertura de linhas **94,55%**, piso 85%
preservado; **28 Node aprovados**. Há avisos de fechamento de conexões na suíte
legada que permanecem para triagem. O ambiente local usa Python 3.13.5/Node 22;
o build e browser devem ser confirmados na CI com as dependências do projeto.

## Pendências e limites

Não há URL pública implantada. Educação 2025 continua sem carga concluída por
ConnectTimeout no download. Nacionalidade do recorte CNES não certifica completude
nem disponibilidade de atendimento. Não há conciliação financeira completa,
avaliação de OCR em corpus oficial, panorama ou validação visual de 3D ao vivo.

O roteiro atualizado, com partes implementadas e restantes, está em `ROADMAP.md`.
A integração nova tem contrato, comandos, fontes e limitações em `RESOURCE_INGESTION.md`.
Cada execução posterior deve registrar o SHA testado e seu resultado real.
