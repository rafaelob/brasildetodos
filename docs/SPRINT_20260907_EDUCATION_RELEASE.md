<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Lote 07/09/2026 — publicação escolar e validação pendente

Base remota conferida: `12d882387732c7da660e5cbf9a9b5f702079ba28`.
Somente main, sem force push; Python 3.14.7 / Node 24.20.0.

A resposta anterior estava desatualizada: a coleta escolar `34078768110`
concluiu no commit `96aa4bf8`. O artefato `10003233969` tem SHA-256
`483bba3a2e71d5360061cbc1880b41c8ab4915e94199a74bb8ac5678ee5fcfe7`.
O relatório informa 214.192 linhas, 138.086 elegíveis e 76.106 excluídas;
todos os registros elegíveis estão sem geometria. Isso não autoriza inventar
endereços, pontos, vagas ou completude externa ao recorte.

## Checklist do lote

- [x] R01 Ler main e AGENTS; recuperar o snapshot e conferir o hash externo.
- [x] R02 Inspecionar o resultado escolar real e a falha da jornada de navegação.
- [ ] R03 Corrigir a espera do teste sem unsafe-eval, bypass de CSP ou remoção de asserções; incluir regressões.
- [ ] R04 Executar novamente Quality e o aceite de dados publicados nos runtimes exigidos.
- [ ] R05 Selecionar, validar e distribuir o catálogo escolar por hash, com relatório e condições explícitas, sem publicar microdados individuais ou dados privados.
- [ ] R06 Instalar o catálogo escolar em banco temporário e exercitar API e interface compilada com registros reais.
- [ ] R07 Publicar nova release sem substituir a v1; confirmar os assets baixados.
- [ ] R08 Reconciliar TODO/ROADMAP/STATUS e evidências, indicando o SHA e as execuções aprovadas.

## Limites que continuam separados

Publicação de código, aprovação de testes, coleta governamental, distribuição de
arquivos e deploy público são resultados distintos. O lote não declara concluídas
as integrações financeiras restantes, corpus oficial de OCR, fotos/panoramas,
validação assistiva e operação pública. Nenhum teste sintético entra nos catálogos.
