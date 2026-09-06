<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Continuidade no main: educação, OCR e catálogo real de saúde

## Regra de trabalho

O PR #1 já foi integrado ao main. Todas as alterações desta continuidade são
publicadas diretamente no main, sem criar outro PR, sem force push e preservando
atualizações concorrentes. A integração prévia e o conector CNES de quarentena
foram encontrados no repositório; não são apresentados como trabalho exclusivo
desta continuação.

## Código publicado nesta continuação

- `95c23eab2ead3d7b25dfdf9b8ce98dbe2010922a`: descoberta da distribuição oficial
  do Censo Escolar por edição, leitura apenas de tabelas escolares, validação
  prévia de encoding/IDs/ano/município/UF, transação e relatório de partições.
  São 44 testes novos. Não criar coordenadas quando estiverem ausentes.
- `c6724cf38019a1c1a4d0938a911cb56bea111392`: OCR local seletivo ligado à revisão
  documental privada, com original preservado, lease atômico, rollback, revisão
  de permissões e recuperação explícita. São 28 testes novos.
- `adc9f15654e9c98a27a8832515733295b1f29e45`: correção dos rótulos dos seletores
  e datalists. A falha foi reproduzida no Chromium; o teste completo de revisão
  documental foi mantido e passou após a correção.

O módulo `bdt.catalog_acceptance` acrescenta quatro testes e verifica um pacote
real pela API, em um banco novo e temporário. Não altera uma instalação existente.
A workflow correspondente permite reproduzir o ensaio com um artefato retido.

## Evidência executada

### Software e colaboração

CI de `adc9f15654e9c98a27a8832515733295b1f29e45`:
https://github.com/rafaelob/brasildetodos/actions/runs/34008376092

Backend, 21 testes Node, build TypeScript/Vite e navegador foram aprovados.
O navegador exercitou pt-BR/en/es, larguras 320/390/1440, favoritos após reload,
fases financeiras distintas e contribuição privada -> revisão por outra pessoa
-> publicação. O ensaio documental adicional percorreu documento nativo ->
texto privado -> proposta de vínculo -> revisão independente -> ficha pública,
seguido de exportação de dados do usuário, retirada de observação e desativação
da conta com invalidação da sessão. As fixtures desse ensaio são sintéticas.

Após adicionar os quatro testes de aceite, a suíte combinada local aprovou
388 testes Python, com cobertura de linhas de 94,91%, e 21 testes Node. Isso
não é uma declaração de qualidade universal nem de completude dos dados.
A CI de cada SHA posterior deve ser consultada separadamente.

### OCR em português

https://github.com/rafaelob/brasildetodos/actions/runs/34008123457

Tesseract 5.3.4 executou uma única página digitalizada sintética em português.
Foram reconhecidos referência de convênio, referência de proposta, valor estimado
em centavos e capacidade prevista. O hash do original foi preservado e o resultado
permaneceu privado e pendente de revisão. A imagem foi inspecionada. Isso comprova
a integração do motor, não sua acurácia em corpus governamental heterogêneo.

### Catálogo real do CNES

Fonte da execução:
https://github.com/rafaelob/brasildetodos/actions/runs/34007758949
Artefato exato: `9981549978`, `cnes-public-catalog-quality-evidence`.

- Arquivo oficial recebido: 56.121.369 bytes.
- SHA-256 da distribuição: `2b09e0978553c05918d3b6ce97ee85819904b56526e1dc6bba385b8edf66c4e6`.
- Última modificação informada pelo servidor: 05/09/2026 06:59:01 GMT.
- 635.118 linhas lidas; 96.123 elegíveis pelo perfil ambulatorial SUS; 538.994
  excluídas pelo perfil; uma em quarentena por nome abaixo do limite de validação.
- 96.116 registros com coordenadas e sete sem coordenadas, ainda pesquisáveis.
- Há registros elegíveis nas 27 UFs. Isso não certifica completude cadastral,
  natureza exclusivamente pública, funcionamento atual ou vagas de atendimento.
- O recorte não pretende representar todos os serviços SUS, inclusive modalidades
  que não atendam ao perfil ambulatorial escolhido.
- 5.571 registros territoriais IBGE foram reutilizados de snapshot verificado;
  suas datas e hashes originais permanecem preservados.

O pacote público foi baixado, teve os arquivos e registros verificados e foi
instalado em um banco novo. A API conferiu todas as partições, fichas e endpoints
privados. O mapa agregou 96.116 registros georreferenciados em 14 grupos no
recorte global testado, sem truncar pela primeira página da lista. Os grupos são
identificados como agregados, não coordenadas de uma unidade. Tiles e 3D ao vivo
não foram certificados por esse teste de contabilidade espacial.

Manifesto público: `beacb31c3c12713fd818db5abbf61e9d10d7088fdc4852af4bb7fdc434595af9`.
A aceitação local terminou em 11,316 segundos; não é benchmark de carga pública.
Relatório resumido: `docs/reports/20260906-cnes-api-acceptance.json`.

### Educação: bloqueio não escondido

https://github.com/rafaelob/brasildetodos/actions/runs/34007812630

A primeira tentativa validou o snapshot territorial e encontrou o link exato da
edição 2025 na página oficial, inclusive o sublinhado final do nome do ZIP. A
página recebida tinha 218.508 bytes, SHA-256
`19b2b5b8d388d16cd89b824467953e440f7a9806c6d12deecdf5ae25d493401a`.
O download da distribuição terminou em ConnectTimeout após tentativas limitadas.
O job foi repetido uma vez e novamente não concluiu a carga. Não foi publicado
um catálogo nacional de escolas, nem usado um ano anterior ou dado fictício como
substituição silenciosa. O processamento continua disponível para execução em
infraestrutura com acesso regular à distribuição oficial.

## Como reproduzir a aceitação do pacote público

```sh
python -m pip install -e '.[test]'
python -m bdt.catalog_release verify /dados/catalog
python -m bdt.catalog_acceptance /dados/catalog --output /evidencias/aceite.json
```

A pasta é a `catalog/` do artefato, não um banco de usuários. A instalação de teste
é temporária e removida depois. Artefatos GitHub expiram: a execução manual futura
deve apontar a IDs exatos de uma versão ainda retida, ou a um pacote verificado
já obtido. Não é necessário reconsultar portais nem possuir chave de modelo.

## Pendências que não foram declaradas concluídas

Ingestão nacional educacional e sua reconciliação; sincronização ampla das fontes
financeiras e de obras; corpus oficial para avaliação de OCR; fontes de panoramas;
validação visual de tiles/3D ao vivo; implantação pública com domínio, backups e
rotina de atualização operacionais. Os ensaios de runtime/containers no runner
não substituem um deploy cloud. Não existe URL pública implantada nesta entrega.

Preservar a distinção entre programa implementado, teste executado, dados
carregados e serviço colocado em produção. O projeto evoluiu, mas não está
apresentado como integralmente concluído.
