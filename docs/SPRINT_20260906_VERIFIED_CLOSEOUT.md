<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Fechamento verificável do lote atual

Base consultada: `cb873ed30750f517042eed4d60471e5ec2d5ee4b`.
Plano publicado em `ec753635`; código aceito em `8324b762`.
Somente main; Python 3.14.7 / Node 24.20.0; sem force push.

A última mensagem da conversa descreveu um estado anterior ao código publicado.
Este plano usa o repositório, os artefatos e a CI como evidência; não reaplica
rascunhos /community sobre a API /groups nem substitui o trabalho existente.

## Checklist

- [x] V01 Consultar main e AGENTS; baixar o snapshot da revisão e verificar seu SHA-256.
- [x] V02 Conferir a implementação integrada e os doze percursos de navegador, incluindo grupos com dois usuários.
- [x] V03 Conferir todos os arquivos já arquivados de OCR contra o manifesto; distinguir originais sintéticos, derivados e documentos oficiais ainda não obtidos.
- [x] V04 Validar a distribuição pública já publicada no GitHub, seu hash externo, entradas selecionadas e aceite de instalação/API.
- [x] V05 Acrescentar regressões e uma validação offline do acervo versionado para impedir deriva entre arquivos, manifesto e documentação de publicação.
- [x] V06 Corrigir falhas encontradas no fechamento, mantendo os gates, os três idiomas e os runtimes fixados.
- [x] V07 Reconciliar TODO, ROADMAP, STATUS e checklist anterior; preservar o histórico e discriminar cada frente realmente pendente.
- [x] V08 Publicar os commits diretamente no main e verificar a CI da revisão funcional resultante.

## Evidências

Quality `34076805060`: 929 testes Python, 95,64% de linhas, build e doze percursos
aprovados. Runtime `34076805106`: PostgreSQL/container aprovados.
Aceite `34076805501`: release baixada, instalada e API consultada em Python 3.14.7.
35 regressões novas; pacote com 96.123 lugares, 6.679 recursos, zero contas ou
observações. Acervo: seis arquivos e manifesto, sem rede ou OCR na conferência.
Recibos e hashes: `reports/20260906-verified-closeout.json`.

## Critério de encerramento

O lote está fechado; os checks não significam conclusão da educação nacional,
todos os conectores, corpus oficial de OCR, avaliação assistiva ou implantação
pública. Nenhuma dessas frentes foi marcada pronta por existir teste sintético.
O TODO atual lista cada trabalho remanescente e mantém o histórico anterior.
