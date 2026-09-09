<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Spike — FNDE/PDDE (sem importador)

Data da inspeção: **2026-09-09**. Sem download dos extratos nacionais
(`.txt.gz`, CSV/XLSX/ZIP de execução). SHA-256 e colunas dos gzip FNDE
permanecem **UNVERIFIED**. Sem alteração de `HOSTS`. Sem conector.

## Conclusão

**Adiar inclusão pública de PDDE no catálogo.** Não ligar `MoneyEvent` a
`Place` (escola Inep) a partir do PDDE Básico.

`CO_ENTIDADE` (chave escolar do Censo Inep) **foi vista** no `$metadata`
OData da **SECADI/MEC**, entidade `PDA_SECADI_PDDE_Campo_Agua`, e numa
linha `$top=1` — isso cobre **PDDE Campo/Água**, ação integrada, não o
repasse anual do PDDE Básico.

O PDDE Básico do FNDE, no DCAT de dados.gov.br e na Plataforma Antonieta,
**afirma** “nível de escola atendida”, mas:

- não há `$metadata` OData público do FNDE com essa coluna (Olinda FNDE
  devolve login ou 404 nos caminhos tentados);
- os artefatos são `exports/PDDE/*.txt.gz` com `link: null` — bytes e
  cabeçalho **não** abertos neste spike;
- o destinatário legal do dinheiro é **UEx / EEx / EM** (CNPJ), não o
  código Inep. EEx (prefeitura/secretaria) recebe pelas escolas públicas
  com até 50 matrículas; um consórcio de até 5 escolas partilha um CNPJ
  de UEx.

Enquanto o gzip Básico não provar `CO_ENTIDADE` (ou equivalente Inep) **e**
a linha for pagamento àquela escola — não estimativa/rede — o produto não
pode declarar pagamento escolar. Também **não** se declara “só
rede/município”: o catálogo oficial do Básico diz o contrário, sem
colunas. Resultado: **adiar**.

Ausência no catálogo é **`not_wired`**, não “zero PDDE no Brasil”.
`GET /api/coverage` não tem família `pdde`; isso não mede o programa real.

## Ponto oficial

Programa (HTTP 200)
(verified 2026-09-09 via
https://www.gov.br/fnde/pt-br/acesso-a-informacao/acoes-e-programas/programas/pdde):

- Resolução CD/FNDE/MEC nº 15/2021; Lei nº 11.947/2009.
- Cálculo de valores: matrículas do **Censo Escolar Inep** do ano
  anterior (escolas públicas e especial privada).
- Destinatários do crédito:
  1. **EEx** — prefeituras e secretarias, escolas públicas com até 50
     estudantes;
  2. **UEx** — caixa escolar / APM / similar, escola (ou consórcio ≤ 5)
     com mais de 50 estudantes;
  3. **EM** — mantenedora de escola privada de educação especial.

Dados abertos FNDE (HTTP 200)
(verified 2026-09-09 via
https://www.gov.br/fnde/pt-br/acesso-a-informacao/dados-abertos):

- PDA-FNDE 2026-2028 (PDF, HTTP 200).
- Catálogo: dados.gov.br, organização FNDE.
- Tutorial Olinda na mesma árvore; o host
  `https://www.fnde.gov.br/olinda-ide/` **não** entrega `$metadata` PDDE
  (ver abaixo).

PDA 2026-2028, Anexo I, base “Apoio Técnico e Financeiro… Dinheiro Direto
na Escola” (verified 2026-09-09 via
https://www.gov.br/fnde/pt-br/acesso-a-informacao/dados-abertos/planos-de-dados-abertos/plano_de_dados_abertos_2026_2028.pdf):
execução financeira PDDE Básico; relação/estimativa de escolas; prestação
de contas; saldos de contas das UEx. Marcada **SIM** no Portal Brasileiro,
periodicidade **mensal**, sem conteúdo sigiloso no inventário.

## URLs abertas (HTTP, licença)

| URL | HTTP | Nota |
|---|---|---|
| https://www.gov.br/fnde/pt-br/acesso-a-informacao/dados-abertos | 200 | PDA, link dados.gov.br |
| https://www.gov.br/fnde/pt-br/acesso-a-informacao/dados-abertos/o-que-se-pode-acessar | 200 | PDDE: execução, escolas, saldos, regularidade |
| https://www.gov.br/fnde/pt-br/acesso-a-informacao/dados-abertos/planos-de-dados-abertos/plano_de_dados_abertos_2026_2028.pdf | 200 | PDF ~1,4 MiB; inventário |
| https://www.gov.br/fnde/pt-br/acesso-a-informacao/dados-abertos/historico-dos-pda-fnde | 200 | PDDE no primeiro PDA (2016) |
| https://www.gov.br/fnde/pt-br/acesso-a-informacao/acoes-e-programas/programas/pdde | 200 | Destinatários UEx/EEx/EM |
| https://www.gov.br/fnde/pt-br/acesso-a-informacao/acoes-e-programas/programas/pdde/acoes-integradas-1 | 200 | Equidade / Qualidade; só UEx |
| https://www.gov.br/fnde/pt-br/assuntos/sistemas/pddeinfo | 200 | Consulta interativa |
| https://www.fnde.gov.br/pddeinfo/pddeinfo/escola/consultar | 200 | Form: `co_escola`, CNPJ, rede, UF, município FNDE |
| https://www.fnde.gov.br/sigefweb/index.php/liberacoes | 200 | Consulta por ano/CNPJ; captcha |
| https://www.fnde.gov.br/dadosabertos/ | **302** | → organização FNDE em dados.gov.br |
| https://www.fnde.gov.br/olinda-ide/ | 200 | Login Olinda (marca BCB); **não** é catálogo público |
| https://www.fnde.gov.br/olinda-ide/servico/DADOS_ABERTOS_FNDE/versao/v1/odata/$metadata | **404** | Caminho histórico; sem EntityType PDDE |
| https://www.fnde.gov.br/olinda-ide/servico/PDDE/versao/v1/odata/$metadata | **404** | Idem |
| https://dados.gov.br/dados/conjuntos-dados/programa-dinheiro-direto-na-escola-pdde | 200 | SPA; conteúdo no RDF |
| https://dados.gov.br/dados/conjuntos-dados/programa-dinheiro-direto-na-escola-pdde.rdf | 200 | DCAT; licença CC-BY |
| https://dados.gov.br/dados/conjuntos-dados/pdde-equidade.rdf | 200 | MEC/SECADI; CC-BY |
| https://dados.gov.br/dados/conjuntos-dados/pdde-campo.rdf | 200 | MEC/SECADI; CC-BY |
| https://dados.gov.br/dados/conjuntos-dados/escola-acessivel--pdde-interativo.rdf | 200 | PDDL; aponta Olinda MEC |
| https://dados.gov.br/api/3/action/package_search?q=PDDE | **401** | CKAN autenticado; RDF usado no lugar |
| https://olinda.mec.gov.br/olinda-ide/servico/PDA_SECADI/versao/v1/odata/$metadata | GET **200** / HEAD **302** login | `$metadata` lido no GET |
| https://olinda.mec.gov.br/olinda-ide/servico/PDA_SECADI/versao/v1/odata/PDA_SECADI_PDDE_Campo_Agua?$top=1&$select=CO_ENTIDADE,NO_ENTIDADE,CO_MUNICIPIO,TP_DEPENDENCIA&$format=json | 200 | Uma linha; não é extrato nacional |
| https://dadosabertos.mec.gov.br/images/conteudo/pdde-equidade/2025/2025_pdde_equidade_dicionario_pda.xlsx | **403** | Cloudflare; dicionário **UNVERIFIED** |
| https://www.fnde.gov.br/plataforma-antonieta-de-barros/dados/produtos-de-dados/visualizar/66 | 200 | SPA Básico público 2025+ |
| https://www.fnde.gov.br/plataforma-antonieta-de-barros-api/products/data-products/66 | 200 | JSON; artefato gzip, `link: null` |
| https://www.fnde.gov.br/plataforma-antonieta-de-barros-api/products/data-products?search=PDDE&size=50 | 200 | 19 produtos públicos |
| https://www.fnde.gov.br/plataforma-antonieta-de-barros-api/products/data-products/11 | **401** | Extrato BB Ágil; não autenticado |
| https://opendefinition.org/licenses/cc-by | 200 | Alvo `dcat:license` do RDF |
| https://creativecommons.org/licenses/by/4.0/deed.pt_BR | 200 | Deed CC BY 4.0 |
| https://www.gov.br/fnde/pt-br/acesso-a-informacao/acoes-e-programas/programas/pdde/consultas | **404** | Caminho inexistente |

`https://www.fnde.gov.br/dadosabertos/` não é um dump: só redireciona ao
portal nacional.

## Licença

RDF do conjunto FNDE “Programa Dinheiro Direto na Escola (PDDE)”
(verified 2026-09-09 via
https://dados.gov.br/dados/conjuntos-dados/programa-dinheiro-direto-na-escola-pdde.rdf):

- `dcat:license` → https://opendefinition.org/licenses/cc-by
- PDDE Equidade e PDDE Campo: o mesmo IRI.
- Escola Acessível – PDDE Interativo: PDDL
  (`https://opendefinition.org/licenses/odc-pddl`).

CC BY permite uso, remix e redistribuição **com atribuição**. Não é o
CC BY-ND do portal FNS. Isso **não** autoriza conector: falta chave
escolar no Básico. Gzip Antonieta (`link: null`) — licença *por arquivo*
**UNVERIFIED**. Conservador: tratar o RDF do conjunto como a licença do
catálogo até existir cabeçalho/dicionário no gzip.

PDA-FNDE 2026-2028 descreve licenças abertas com atribuição da fonte
(verified 2026-09-09 no PDF citado). Código AGPL do repositório **não**
relicencia PDDE.

## `CO_ENTIDADE` / `CO_ESCOLA` / Inep

### Visto (SECADI — não é PDDE Básico)

GET `$metadata` (verified 2026-09-09 via
https://olinda.mec.gov.br/olinda-ide/servico/PDA_SECADI/versao/v1/odata/$metadata):

Entidade `PDA_SECADI_PDDE_Campo_Agua` inclui, entre outras:

`CO_MUNICIPIO`, `NO_UF`, `SG_UF`, **`CO_ENTIDADE`**, **`NO_ENTIDADE`**,
**`TP_DEPENDENCIA`**, mais colunas largas `EMPENHADAS_*` / `PAGAS_*` /
`VALOR_*` por ano.

`$top=1` (verified 2026-09-09; uma linha, sem extrato nacional):

```json
{"CO_MUNICIPIO":"1100205","CO_ENTIDADE":"11001151",
 "NO_ENTIDADE":"EMEF HEITOR VILLA LOBOS","TP_DEPENDENCIA":"Municipal"}
```

Oito dígitos em `CO_ENTIDADE`, com `NO_ENTIDADE` e `TP_DEPENDENCIA` no
mesmo perfil que o Censo Escolar. **Não** se cruzou esta linha com o
catálogo Inep desta instalação.

A mesma `$metadata` tem `INEP` (não o nome `CO_ENTIDADE`) em
`PDA_SECADI_Escola_Acessivel` e `PDA_SECADI_Sala_de_Recursos*` — ações
SECADI, série curta / “valor destinado”, não PDDE Básico.

### Não visto no Básico FNDE

- `$metadata` Olinda FNDE: **não aberto** (404 / login).
- Gzip `PDDE_Execucao_Financeira_PDDE_Basico_Publico.txt.gz` (Antonieta
  produto 66) e pares: **não baixados**. Colunas **UNVERIFIED**.
- Dicionário Equidade 2025 (XLSX MEC): HTTP 403 Cloudflare — **UNVERIFIED**.
- PDDE Info: campo HTML `co_escola`, rótulo “Código da Escola”. **Não**
  está escrito que é Inep/`CO_ENTIDADE`. Equivalência **UNVERIFIED**.
- SIGEF liberações: filtro por **CNPJ** da entidade, não por escola.
- Extrato BB Ágil (Antonieta id 11): API **401**. Colunas **UNVERIFIED**.

Prosa de catálogo **não** substitui nome de coluna.

## Granularidade — não anexar PDDE a Place sem evidência

Contrato: `backend/bdt/domain.py` `MoneyEvent` — `facility_id` exige
`relation_state` `direct` ou `reviewed` **e** `evidence`. Territorial
não admite estabelecimento.

| Recorte | O que a fonte sustenta | Place / escola |
|---|---|---|
| PDDE Básico (gzip FNDE) | Catálogo: UF + rede **até escola**; bytes **UNVERIFIED**. Crédito legal: UEx/EEx/EM | **Não** ligar. EEx = município/rede para escolas ≤ 50. Consórcio ≤ 5 escolas / um CNPJ |
| Saldos UEx | Conta da unidade executora (produto Antonieta 68–71) | Destinatário = UEx, não pino escolar |
| Prestação de contas | Situação UEx e EEx (produto 59) | Entidade, não Place |
| PDDE Campo/Água (Olinda MEC) | `$metadata` + `$top=1` com `CO_ENTIDADE` | Chave escolar **existe**; valores empenhados/pagos em colunas anuais largas — **não** importado. Não rotular como PDDE Básico |
| PDDE Equidade 2025 (CSV MEC) | RDF fala em “quantidade de escolas” e valores de custeio/capital; ficheiros 403 | Agregado vs linha escolar **UNVERIFIED** |
| PDDE Info / SIGEF | Consulta pontual (escola ou CNPJ); captcha no SIGEF | Não é ingestão em lote |

Nome da escola, município ou proximidade **não** geram `facility_id`.
Censo Inep nesta instalação **não** implica pagamento PDDE.

Execução Básico 2025+ é **acumulativa no ano** (o catálogo diz: maio =
soma janeiro–maio). Somar competências como `nature=event` seria dupla
contagem — confirmar só depois das colunas.

## Produtos Antonieta (metadado JSON, sem gzip)

`GET …/products/data-products?search=PDDE&size=50` → 19 itens
`Publicado` (verified 2026-09-09). Artefatos `exports/PDDE/*.txt.gz`,
`type: AUTO_STORING`, `link: null`. Nenhum gzip foi pedido.

Famílias: estimativa/relação de escolas; execução financeira
público/privado (2025+ e cortes até 2024 / anos 2021–2024); saldos UEx;
prestação de contas SIGPC.

Produto 4 (PDDE Info) é ligação ao sistema de consulta, não tabela.
Produto 11 (extrato BB) recusou sem autenticação.

## Mapeamento `MoneyEvent` (hipótese, sem ingestão)

| Campo | Se um dia houver importador | Porquê |
|---|---|---|
| `perspective` | `executing_unit` na UEx; `municipal` / `state` na EEx | Destinatário do crédito, não a União pagadora |
| `facility_id` | `None` no Básico até coluna Inep **e** linha = aquela escola | EEx e consórcio quebram 1:1 |
| `relation_state` | `territorial` enquanto `facility_id` for nulo | `domain.py` |
| `recipient` | CNPJ/nome da UEx, EEx ou EM | Não inventar escola |
| `municipality_id` | IBGE7 se a coluna existir e for 7 dígitos | `$top=1` Campo/Água usou 7 dígitos; Básico **UNVERIFIED** |
| `phase` | transferência/pagamento — nome de coluna **UNVERIFIED** | |
| `nature` | Básico 2025+: `cumulative` se o texto do catálogo se confirmar | Não somar meses |
| `source.dataset` | não atribuir agora | Sem conector; não reutilizar `inep` |

`perspective=federal` descreveria o FNDE pagador, não o recorte
publicado.

Campo/Água com `CO_ENTIDADE` **ainda não** vira conector: é fatia SECADI,
formato largo, `$top=1` não valida população nem unidade monetária.

## Allowlist HTTPS

`backend/bdt/ingest.py` `HOSTS` **não** contém `www.fnde.gov.br`,
`olinda.mec.gov.br`, `dados.gov.br`, `dadosabertos.mec.gov.br` nem
`plataforma-antonieta-de-barros-api`. Este spike **não** altera `HOSTS`.
Sem importador, a lacuna é irrelevante.

## O que isto não é

- Não é Censo Escolar Inep nem cobertura de escolas.
- Não é Transferegov/convênio (PDDE é transferência automática).
- Não é FUNDEB, PNAE nem PNATE.
- Não certifica competência 2026 completa.
- Prosa “até o nível de escola” **não** é `CO_ENTIDADE` no gzip Básico.
- `CO_ENTIDADE` em Campo/Água **não** autoriza pintar o Básico no mapa.

## Próximo passo (não nesta missão)

Reabrir só se o OWNER (1) autorizar leitura **do cabeçalho** de **um**
gzip Básico (não o país) e o dicionário nomear `CO_ENTIDADE` / código
Inep **e** o destinatário da linha, ou (2) pedir fatia explícita
Campo/Água com a chave já vista no `$metadata`, sem chamar isso de PDDE
Básico. Aí: hash, dicionário, EEx vs escola, `cumulative` vs `event`.
Nada disso está autorizado agora.
