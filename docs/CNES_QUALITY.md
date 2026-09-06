<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# CNES: validação completa do arquivo e quarentena explícita

A carga real de 2026-09-06 UTC baixou a distribuição de 56.121.369 bytes do endereço publicado no catálogo oficial. O arquivo contém 635.118 linhas; a tentativa inicial de importação estrita falhou em um nome vazio. O download concluído não demonstrou a importação nacional. O hash observado foi `2b09e0978553c05918d3b6ce97ee85819904b56526e1dc6bba385b8edf66c4e6`. Esses números são daquela versão; a nova execução deve relatar seus próprios valores.

O perfil continua sendo **atendimento ambulatorial SUS declarado, sem motivo de desabilitação preenchido**. Isso não cobre todo atendimento SUS, não identifica somente UBS nem confirma disponibilidade atual de consulta. A distribuição inspecionada não tem data de atualização por linha: a data da coleta nunca é usada como se fosse data do fato.

## Não relaxar as regras de domínio

`bdt.cnes_quality` faz pré-validação antes de chamar o importador estrito existente. Nome vazio não vira um nome inventado. Código municipal desconhecido não é completado por aproximação. Coordenadas inválidas continuam nulas, com a unidade pesquisável quando os outros campos forem válidos.

Schema diferente, significado desconhecido do código SUS e identidades repetidas bloqueiam todo o lote. Defeitos isolados de registro geram quarentena. O padrão aceita **zero** rejeições. Uma execução pode receber limites explícitos de quantidade e proporção; ambos precisam ser atendidos. A pipeline de evidência usa até 100 rejeições **e** até 0,1% das linhas. Isso é um orçamento operacional para produzir um subconjunto útil, não uma certificação de qualidade nem uma alteração dos validadores.

Se houver qualquer quarentena permitida, a importação recebe `partial_quality`. A cobertura mostra `source_read` e `quarantined`. O produto não declara a fonte totalmente representada e não elimina silenciosamente registros prévios inválidos nesta edição. Ausência ou defeito não são confundidos com desativação do estabelecimento.

O relatório contabiliza todas as linhas: elegíveis, excluídas pelo perfil e em quarentena. Os diagnósticos identificam número da linha, código institucional quando válido, hash do registro e nomes dos campos com erro. Não copiam a linha completa, e-mails ou textos de exceção contendo dados pessoais.

## Artefato público e verificação

O script `ops/cnes_quality_catalog.py` utiliza um diretório novo. Pode receber `BDT_TERRITORY_SNAPSHOT`, preservando a proveniência do IBGE previamente coletado, ou buscar diretamente a fonte territorial. O workflow de evidência seleciona explicitamente um artefato territorial de uma execução conhecida. Ele expira; não é uma dependência de produção permanente nem um fallback secreto.

A carga gera uma release pelo exportador de tabelas públicas e instala esse pacote em outro banco novo para testar a ida e volta. Não publica contas, sessões ou contribuições. O banco temporário e o ZIP original não entram no artefato público.

`national_catalog_certified` permanece `false` mesmo se existirem unidades em 27 UFs. As contagens comprovam o que foi carregado daquele arquivo e perfil, não equivalência com todo o SUS ou validação física dos serviços. Dados e condições de reutilização continuam vinculados à fonte oficial.

```bash
python -m pytest backend/tests/test_cnes_quality.py
# Execução real, com controle de orçamento e origem explícitos pelo operador:
BDT_CNES_OUTPUT=data/cnes-new-run \
BDT_MAX_QUARANTINED=0 BDT_MAX_QUARANTINED_FRACTION=0 \
python ops/cnes_quality_catalog.py
```

Fonte: https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/CNES/cnes_estabelecimentos_csv.zip
Evidência da falha inicial: https://github.com/rafaelob/brasildetodos/actions/runs/34006936145
