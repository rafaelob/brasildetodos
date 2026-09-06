<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Evidência desta implementação inicial

## Código e testes efetivamente executados

Revisão de código: **4e60bc2c46a7a93a1e5e43e88711e191cb0ee78e**.
CI: https://github.com/rafaelob/brasildetodos/actions/runs/34004360798

- Backend aprovado: 119 testes, cobertura de linhas aproximadamente 91% (91,33% na medição detalhada anterior com os mesmos módulos). Não é prova universal de comportamento.
- Web aprovado: 10 testes de idiomas/helpers e compilação TypeScript/Vite.
- Browser aprovado: interface compilada contra API real em localhost no runner e banco temporário sintético. Larguras 320, 390 e 1440, três idiomas, ausência de overflow horizontal, favoritos persistentes após reload e fases financeiras separadas.
- Colaboração aprovada no navegador: usuário envia observação privada, pessoa diferente revisa e a contribuição aprovada aparece publicamente na ficha. Não há substituição de dados oficiais.
- Artefato browser-evidence (ID 9980483946) contém capturas e result.json; todos os registros dessas capturas são explicitamente sintéticos.
- PDF nativo sintético extraído sem OCR, com posições e referência candidata; original preservado. Importações locais testam rollback, duplicidade, elegibilidade e histórico.

Falhas iniciais do teste de navegador foram resolvidas sem remover os testes do fluxo: readiness passou a usar elementos renderizados, não network-idle; a confirmação de envio é verificada dentro da região acessível de status, que também contém um botão de fechar.

## Dados oficiais: resultados separados da suíte determinística

Execução https://github.com/rafaelob/brasildetodos/actions/runs/34004055769:

- IBGE: 5.571 registros municipais importados da resposta oficial, 2.470.036 bytes, SHA-256 86ecdccdf97d72e7e5e46f0854cfcea8bacc28154cc1bc4ed0e6110e3a6c9c02.
- CNES: resposta padrão de 8.117 bytes, SHA-256 f2a6e47454afb645606812499528eafb2f522c384b8019eb4f460d68befd3f58; cinco registros lidos, cinco excluídos pelo perfil de atendimento ambulatorial SUS. Isso não é carga nacional CNES.
- O banco do probe é temporário; esses dados não foram publicados em uma instância de produção.

Na execução mais recente (34004360798), IBGE voltou a apresentar ConnectTimeout; CNES respondeu novamente. O probe de fontes é informativo e usa continue-on-error. Portanto, aprovação dos testes da aplicação não deve ser apresentada como aprovação irrestrita das integrações externas. Houve oscilação real entre sucesso e timeout, registrada nos artefatos.

No ambiente local de construção, DNS impediu downloads externos; Chromium local bloqueou navegação localhost por política. Os testes de interface foram executados no runner GitHub, sem desabilitar a política do ambiente local.

## O que não foi concluído

- Ingestão nacional de escolas/saúde, reconciliação completa de partições e cobertura certificada.
- Sincronização integral PNCP/Transferegov/Obrasgov, editor documental e vínculos revisados em escala.
- OCR de corpus oficial digitalizado e qualidade por campo.
- Renderização de tiles/3D ao vivo, panoramas, Safari físico e avaliação integral de acessibilidade.
- Docker/PostgreSQL/migrações, backup/restauração e implantação pública cloud.
- Lockfile gerado pela CI ainda não foi incorporado ao repositório; builds transitivos não estão totalmente travados.
- Políticas/fluxos completos de retenção, exclusão e revisão posterior de contribuições antes de abertura ampla.

A aplicação inicia vazia e não publica fixtures. Issues #2 a #5 descrevem os próximos gates. Esta atualização é apenas documental; a revisão de código testada está identificada acima.
