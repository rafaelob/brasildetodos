<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Evidência desta implementação inicial

## Executado localmente

119 testes Python passando; 91% de cobertura de linhas medida, não prova universal de comportamento. Dez testes Node de idiomas, referências e exibição monetária. Fluxo de API de submissão privada, revisão independente e publicação testado. PDF nativo sintético foi extraído sem OCR e com original preservado.

## GitHub Actions efetivamente observado

Execução https://github.com/rafaelob/brasildetodos/actions/runs/34003855224 sobre b0b69e91d85a800b61f77704738fe159422f5a36:
- Backend: aprovado, incluindo o gate de cobertura.
- Web: npm test e TypeScript/Vite build aprovados. Artefato web-build contém dist e o package-lock gerado.
- Probe oficial: CNES baixado (8.117 bytes; SHA-256 f2a6e47454afb645606812499528eafb2f522c384b8019eb4f460d68befd3f58), cinco registros lidos e cinco excluídos pelo recorte SUS. Não houve publicação de lugares dessa amostra.
- IBGE: ConnectTimeout no runner. A tarefa de fontes falhou e é informativa/continue-on-error; isso NÃO equivale a certificação nacional nem deve ser ocultado pelo resultado global da CI.

Adicionada suíte de navegador em ops/browser_smoke.py com API real local, banco temporário sintético, três larguras e fluxo de colaboração. A execução ainda precisa ser confirmada nos jobs da revisão que introduz essa suíte. Navegação localhost no Chromium deste ambiente local foi bloqueada por política do ambiente; não desabilitamos essa política.

## Pendências

Ingestão nacional, perfis integrais de portais, OCR de corpus oficial, editor documental e cloud deployment. Docker/PostgreSQL, restauração e política pública de colaboração precisam de validação. Mapa/tiles/3D ao vivo e Safari físico não foram certificados. Lockfile gerado pela CI ainda precisa ser incorporado ao repositório para builds totalmente travados.

A aplicação inicia vazia; fixtures sintéticas existem apenas em testes. Código e documentação distinguem capacidades implementadas, fontes inspecionadas e integrações ainda não concluídas. Issues #2 a #5 registram os próximos gates.
