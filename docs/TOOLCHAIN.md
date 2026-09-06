<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Toolchain do Brasil de Todos

Versões escolhidas pelo proprietário em 2026-09-06:
**Python 3.14.7** e **Node.js 24.20.0**. A publicação oficial das duas versões
foi consultada. Não usar a série genérica 3.14/24 como comprovação de patch.

## Única configuração coerente

`.python-version` é lido pelos jobs Python; `.nvmrc` pelos jobs Node.
`.node-version` dá suporte a gerenciadores que usam esse nome. `pyproject.toml`
e `web/package.json` declaram os mesmos alvos. `web/.npmrc` exige o engine.
Docker fixa as duas imagens por versão e confere o executável durante o build.
Os testes de configuração detectam deriva nos arquivos e em cada setup de CI.

```sh
python --version
node --version
python ops/check_toolchain.py --runtime python
node ops/check-node.mjs
python -m venv .venv
# Ativar .venv conforme o shell e o sistema operacional.
python -m pip install -e '.[test,postgres]'
python -m pytest
cd web
npm run check:runtime
npm ci  # requer o lockfile verificado; geração inicial é descrita abaixo
npm test
npm run build
```

Para uma árvore que ainda não contém `web/package-lock.json`, a geração inicial
é `npm install`. Não apresentar essa instalação como reprodução transitiva exata.
O workflow `dependency-lock.yml` gera o lock sob Node 24.20.0, testa, compila,
executa auditoria e só publica se o manifesto continuar igual. Uma falha de
vulnerabilidades impede a publicação; não adicionar exceções silenciosas.

## Evidência, não fallback

`python ops/check_toolchain.py --runtime config` apenas verifica arquivos. Serve
para avaliar a alteração em um ambiente que ainda não tenha os runtimes, mas não
substitui execução dos testes em Python 3.14.7. Os modos python/node/all também
conferem o executável. Sem a versão solicitada, retornam falha explícita.

CI mantém o piso de cobertura e as jornadas de navegador. Ensaios de OCR e
PostgreSQL têm evidências próprias. Falha de fonte oficial, dados carregados e
deploy não se confundem com testes aprovados. Sem publicação ou operação cloud
nova implícita nesta migração.

## Atualizações posteriores

Patches futuros exigem alteração coordenada dos arquivos de versão, metadados,
imagens e guardas, com testes. Não alterar registros históricos de testes que
rodaram em Python 3.13/Node 22. Artefatos devem informar a revisão do código.
A versão fixa não substitui digests de imagens, lockfiles Python ou avaliação
de dependências; esses controles continuam rastreados no TODO.

## Referências

- https://www.python.org/downloads/release/python-3147/
- https://nodejs.org/en/download/archive/v24.20.0
- https://github.com/actions/setup-python
- https://github.com/actions/setup-node/blob/main/docs/advanced-usage.md
