<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Instalação conjunta — saúde, educação e recursos

Base: `3160438e735a838daa87db5aed042dc2ec1ace2c`.
A release escolar `education-2025-20260907-v1` já foi publicada e revalidada na
execução `34088190338`. Não repetir a coleta nem substituir a release anterior.

- [x] C01 Confirmar as duas distribuições selecionadas, com hashes externos e origens independentes.
- [ ] C02 Implementar uma instalação conjunta em banco NOVO, sem abrir ou sobrescrever banco de usuários.
- [ ] C03 Reutilizar apenas municípios idênticos; recusar conflitos de identidade, estado, fonte ou código, sem vincular saúde e escola por nome/proximidade.
- [ ] C04 Preservar integralmente payloads/históricos e versões de recursos, sem somar fases ou transformar contratos em pagamentos.
- [ ] C05 Testar colisões, falhas transacionais, substituição de arquivos, sidecars, histórico e privacidade.
- [ ] C06 Instalar os dois pacotes reais no runner, conferir filtros/contagens e executar a interface sobre o catálogo misto.
- [ ] C07 Commit/push no main, verificar CI, atualizar TODO e documentar operação e limitações.

Resultado esperado desta seleção: 96.123 registros de saúde + 138.086 escolares,
sem inferir coordenadas para escolas; 6.679 recursos cadastrais mantidos. Isso não
é relacionamento entre unidades, total de beneficiários ou certificação de cobertura.
As distribuições originais e as datas de referência continuam separadas e intactas.
