<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Evidência desta implementação inicial

## Executado localmente

- 119 testes Python passando; cobertura de linhas medida 91%, não cobertura universal de comportamento.
- 10 testes Node de paridade pt-BR/en/es, links seguros e exibição monetária.
- Fluxo API completo: login → observação pendente → revisão por outra pessoa → publicação; isolamento e rejeição testados.
- PDF digital sintético: extração nativa, posições e referência candidata; original preservado e nenhum OCR invocado.
- Importações sintéticas: transação, duplicidade, município desconhecido, ineligibilidade e histórico.
- Arquivos de código são reais e executáveis. Não são apenas exemplos de documentação.

## Verificado por consulta externa

- Repositório inicial continha somente README; branch própria a partir do commit 6a3b905033b9e1fd3cc9a3771f980c28035a7b72.
- JSON CNES efetivo usa estabelecimento_faz_atendimento_ambulatorial_sus; amostra consultada contém cinco registros com NAO, alguns com esfera MUNICIPAL e referência individual 2025-09-03. Não ingestamos essa amostra como cobertura nacional.
- IBGE estados retorna as 27 UFs; isto não valida a carga integral de municípios.
- Documentação MapLibre demonstra extrusão de edificações; integração ao vivo e cobertura 3D não foram certificadas.

## Não executado / não concluído

- Ingestão nacional e atualização automática de cada fonte.
- OCR de documentos oficiais digitalizados; corpus de qualidade de OCR por campo.
- Download programático externo no ambiente local: resolução DNS falhou. Navegador de pesquisa conseguiu consultar os recursos citados.
- Build npm local inicialmente bloqueado pela resolução DNS do registry. CI foi configurado para compilar; resultado deve ser consultado no PR, não presumido.
- Docker/PostgreSQL/cloud deployment, TLS, telefone real, Safari físico e revisão completa de acessibilidade.
- Sem dados reais carregados, frontend apresenta estado vazio e a cobertura real do banco.

Atualizar este registro com IDs de execução e resultados efetivamente observados. Não substituir pendências por estimativas otimistas.
