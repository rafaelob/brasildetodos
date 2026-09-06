<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Catálogos públicos verificáveis

O banco da aplicação pode conter contas, sessões e contribuições privadas. Ele **não é um artefato público**. O módulo `bdt.catalog_release` exporta uma lista explícita de tabelas de dados públicos: municípios, lugares, registros financeiros, recursos e histórico cadastral. Não exporta contas, sessões, observações, auditoria de moderação, originais/extrações de documentos, identidades de revisores nem vínculos documentais. Esses últimos exigem uma política de portabilidade de proveniência própria; não são reduzidos a vínculos sem fundamento.

A exclusão dessas tabelas não anonimiza automaticamente os campos das fontes oficiais. O operador continua responsável por revisar conteúdo e condições de reutilização antes de publicar. Licenças dos dados e atribuições permanecem válidas; AGPL não relicencia dados de terceiros.

## Exportar, verificar e instalar

Execute no ambiente de ingestão, não durante uma requisição web:

```bash
python -m bdt.catalog_release export \
  --database sqlite:///data/catalog.db \
  --output releases/catalog-20260906 \
  --revision "$(git rev-parse HEAD)"
python -m bdt.catalog_release verify releases/catalog-20260906
python -m bdt.catalog_release install releases/catalog-20260906 \
  --output data/catalog-new.db
```

A exportação admite SQLite e PostgreSQL. O caminho PostgreSQL usa leitura repetível; deve ser exercitado nos testes de integração da instalação. A instalação inicial gera SQLite; não migra um banco PostgreSQL nem substitui um banco existente. Sem `--revision`, o manifesto registra explicitamente `development`, não atribui um SHA imaginário.

**Nunca aponte a instalação para o banco ativo.** O destino precisa ser novo. O instalador cria um banco temporário, valida chaves estrangeiras, estados dos municípios e integridade, fecha o WAL e publica sem sobrescrever arquivos existentes. Credenciais e contas não são transferidas. Antes de usar uma instalação nova, o operador configura o acesso administrativo pelo fluxo existente. Um catálogo vazio permanece vazio, não vira demonstração sintética.

## Conteúdo e integridade

Cada arquivo JSONL possui nome fixo, número de linhas, tamanho e SHA-256. As linhas são validadas com os modelos do domínio, incluindo coerência entre payload e índices, campos financeiros, identidade e histórico. Partições por dataset/UF são recalculadas na verificação: não basta escrever uma contagem no manifesto. Há limites por linha, arquivo, quantidade de registros e conjunto. Arquivos simbólicos e formatos inesperados são recusados.

O manifesto contém a revisão do software, origem dos dados, referências temporais e exclusões. Os hashes provam integridade em relação ao manifesto, **não autenticidade da fonte nem assinatura do publicador**. Só instale releases de origem confiável; um atacante pode substituir dados e manifesto juntos.

A exportação mantém uma visão consistente do banco. Não modifica os registros de origem nem inclui uma cópia indiscriminada das tabelas. A instalação utiliza uma única transação para o conjunto público; uma falha não publica o banco temporário.

## Cobertura e finanças

`national_catalog_certified` permanece `false`: processar todas as linhas disponíveis não demonstra que a distribuição representa o país inteiro, e exportar dados não cria essa prova. Use os relatórios de coleta e reconciliação territorial para a análise de cobertura. Manifestos de ingestão e evidências operacionais ficam separados deste formato público; não são recriados como importações oficiais fictícias.

Eventos financeiros preservam fase, perspectiva, destinatário, instrumento, período e natureza. Pagamento e transferência não são fundidos. Históricos cadastrais mantêm seus campos e datas; uma atualização de coleta não gera uma nova intervenção.

## Testes

```bash
python -m pytest backend/tests/test_catalog_release.py
python -m pytest --cov=bdt --cov-fail-under=85
```

Os testes usam registros sintéticos isolados. Eles cobrem ida e volta, ausência de contas/observações, falha de integridade, manifesto alterado, chaves estrangeiras, inconsistência de campos, estados, preservação de fases financeiras e recusa de destinos existentes. Não comprovam ingestão nacional, disponibilidade dos portais, licença dos dados ou implantação pública.
