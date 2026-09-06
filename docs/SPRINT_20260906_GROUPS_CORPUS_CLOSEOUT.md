<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Lote de fechamento: grupos integrados e evidências documentais duráveis

Base conferida: `2ac1eb18f5ac02031ce039d835f5b6c97e1c67b3`.
Python 3.14.7 / Node 24.20.0. Trabalho apenas no main, sem force push.
Não substituir o backend publicado pelo rascunho anterior: aquele rascunho usa
/community e campos incompatíveis com o contrato atual /groups.

## Checklist executável

- [x] C01 — Conferir main, AGENTS e CI; recuperar snapshot com hash verificado.
- [x] C02 — Identificar a divergência entre o rascunho da interface e a API atual.
- [ ] C03 — Implementar navegação e interface de grupos privados no contrato atual:
  criar/editar, convites, membros, transferência, arquivamento, saída e tarefas.
- [ ] C04 — Fechar tarefa ponta a ponta: localizar lugar, assumir, criar e
  compartilhar observação própria, revisar independentemente, reabrir/cancelar.
- [ ] C05 — Cobrir conflitos, respostas atrasadas, sessão, consentimento, revisão,
  persistência e privacidade; manter gates e percursos existentes.
- [ ] C06 — Executar build e browser multiusuário PT/EN/ES em 320/390/1440 pixels
  nos runtimes fixados, corrigindo o produto e não removendo verificações.
- [ ] C07 — Inventariar os artefatos locais baixados e os documentos usados no OCR;
  separar originais oficiais, excertos manuais e fixtures sintéticas.
- [ ] C08 — Publicar no GitHub somente arquivos inspecionados e autorizados,
  incluindo manifesto, hashes, proveniência e resultados; não expor dados privados.
- [ ] C09 — Exigir verificação reproduzível do corpus: bytes originais preservados,
  saída de extração diferenciada e nenhum resultado sintético no catálogo público.
- [ ] C10 — Conferir coleta educacional e intake oficial atual; executar tentativas
  delimitadas e registrar resultado sem confundir reuso com nova coleta.
- [ ] C11 — Reconciliar TODO, ROADMAP, STATUS e matriz de funcionalidades com
  referências de commits, CI, artefatos e pendências concretas.
- [ ] C12 — Confirmar publicação no main e resultado das verificações da revisão.

## Inventário inicial, ainda sem publicação documental

O arquivo recuperado `brasildetodos-ocr-portuguese-evidence.zip` contém
SYNTHETIC-native.pdf, SYNTHETIC-scanned.pdf, SYNTHETIC-page.png e result.json.
São fixtures sintéticas de validação, não convênios oficiais. O pacote inicial
conferido_fase1 contém excertos transcritos e candidatos, não os PDFs oficiais.
Cada arquivo deve ser inspecionado antes de sua republicação. O acesso público
à origem não elimina obrigações de privacidade, atribuição e licenciamento.

## Demais frentes mantidas no plano, não encerradas pelo lote

Educação nacional e reconciliação dos denominadores; competências CNES;
Transferegov completo, Obrasgov físico/geometrias, PDDE/FNS, conciliação financeira;
corpus oficial OCR, fila/cancelamento/retenção; fotos e panoramas; testes externos
mapa/3D; acessibilidade assistiva/dispositivos; atualização durável, domínio/HTTPS,
monitoramento, backups/restauração, rollback e operação pública.

Código, teste automatizado, coleta real, material disponibilizado no GitHub e
aplicação implantada são resultados separados. Fixtures isoladas são necessárias
para regressões e jamais substituem dados reais em produção. Sem LLM obrigatório.
