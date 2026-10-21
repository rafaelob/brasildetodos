# Contribuir com o Brasil de Todos

Obrigado por querer ajudar. O projeto separa **fato oficial**, **observação
cidadã**, **candidato extraído** e **vínculo revisado**. Uma contribuição é
bem-vinda quando preserva essa separação e deixa claro o que foi verificado.

## Antes de abrir uma issue

1. Procure issues abertas e a documentação em `docs/`.
2. Para uma falha, descreva reprodução, comportamento esperado, comportamento
   atual, ambiente (SQLite/PostgreSQL, Docker/local) e logs **sem dados
   pessoais ou segredos**.
3. Para uma fonte de dados, informe URL oficial, licença/condições de uso,
   data de referência, campos, cobertura, periodicidade e uma amostra mínima.
4. Para segurança, **não** abra issue pública com detalhes de exploração. Use
   [SECURITY.md](SECURITY.md).

## Formas de contribuir

- corrigir documentação, exemplos e traduções pt-BR/en/es;
- adicionar testes de comportamento, restauração, acessibilidade ou regressão;
- revisar fontes oficiais, licenças e perfis de importação;
- melhorar a interface sem esconder ausência de dados;
- revisar código, segurança e desempenho;
- reproduzir falhas em ambiente limpo e relatar o resultado.

Tarefas marcadas com `good first issue` são um bom começo. Tarefas de dados ou
privacidade podem exigir revisão de um mantenedor antes do código.

## Ambiente local

Requisitos fixados: Python **3.14.8** e Node.js **24.20.0**.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
bdt init-db
cd web
npm ci
npm run build
cd ..
python -m pytest
```

Para PostgreSQL local:

```bash
docker compose -f docker-compose.postgres.yml up --build -d
curl http://127.0.0.1:8009/api/health
```

O stack local não é produção. Leia [Operação](docs/OPERATIONS.md) e
[Migrações](docs/MIGRATIONS.md).

## Testes e evidência

- Rode `python -m pytest` e, em `web/`, `npm test` e `npm run build`.
- Inclua um teste comportamental para a mudança; não apenas um teste de forma.
- Não baixe validações, cobertura, autorização ou limites para fazer um teste
  passar. Se um dado oficial não fecha, deixe a falha visível.
- Relate o SHA testado e se algum teste não foi executado.

## Dados, privacidade e conduta

- Nunca anexe senhas, tokens, CPF, prontuários, fotos de crianças/pacientes ou
  documentos originais em issue/PR pública.
- Não invente coordenadas, vínculos, valores, datas ou cobertura.
- Preserve fonte, ID do registro, data de referência, data de coleta e hash.
- Não publique extração de PDF ou foto automaticamente; moderação é separada.
- Seja respeitoso. Divergência técnica é bem-vinda; perseguição, exposição
  pessoal e acusação sem verificação não são. Leia o
  [Código de Conduta](CODE_OF_CONDUCT.md).

## Fluxo de contribuição

O mantenedor atual integra o trabalho em `main` por decisão do proprietário.
Contribuições externas podem começar por uma issue focada e, se houver código,
por um PR pequeno ou patch anexado. Não faça force-push em `main` e não
sobrescreva trabalho concorrente. Agentes automatizados devem seguir
`AGENTS.md` (somente `main`, sem branches/PRs).

Use commits com sign-off (`git commit -s`) para declarar o
[Developer Certificate of Origin](https://developercertificate.org/). O sign-off
declara o direito de submeter a contribuição; não transfere direitos autorais.

Um PR deve explicar problema, mudança, riscos, rollback, testes executados e
impacto em dados/privacidade. Mudanças grandes devem ser divididas em fatias
revisáveis.

## Revisão

A revisão verifica correção, testes, segurança, privacidade, acessibilidade e
honestidade dos dados. A aprovação de uma contribuição não certifica a situação
física de uma instituição nem transforma uma release histórica em catálogo vivo.
