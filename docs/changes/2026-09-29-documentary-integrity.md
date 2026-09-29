<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Evidência documental significativa — Issue #4

A API já recusava campos feitos só de espaços nas propostas novas. Porém, a
validação de publicação aceitava um trecho vazio depois da normalização quando
ele já estava armazenado: a string vazia é substring de qualquer página, até de
uma página sem texto. O teste de integração reproduziu publicação HTTP 200 desse
candidato legado; agora a revisão retorna HTTP 422, mantém estado e revisão do
candidato e não cria evento de aprovação nem vínculo público.

A proposta passa a medir os mínimos de trecho/justificativa depois de normalizar
espaços, inclusive internos, sem reescrever o layout original armazenado. A nota
de revisão recebe a mesma proteção. O validador documental repete o mínimo do
trecho para proteger chamadas internas e registros legados. Hashes esperados
nulos, vazios ou fora do formato SHA-256 também invalidam o pacote, mesmo que os
dois campos defeituosos sejam iguais.

Regressões: `backend/tests/test_evidence_whitespace.py`; oito casos falharam na
revisão-base `f95c43955d95b2bf800535729f9b5f8099f4bd5b`.
Comando: `python -m pytest backend/tests/test_evidence.py backend/tests/test_features.py backend/tests/test_evidence_whitespace.py`.

Nenhum OCR foi executado e nenhum original foi alterado. Transcrição, pertinência
institucional e autorização de publicação continuam decisões distintas, com
revisão independente. Corpus oficial, avaliação por campo, fila persistente,
quotas e política de retenção continuam fora deste recorte da Issue #4.
