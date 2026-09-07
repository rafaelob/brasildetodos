<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Próximo lote: coleta escolar verificável

Base consultada: `7109212283dc886dcfd6481d46354da79b83531e`. Somente main; sem force push.
Python 3.14.7 e Node 24.20.0 continuam obrigatórios na aceitação.

## Problema e hipótese

D01/D02 estão abertos: o download da edição escolar 2025 falhou com validação TLS código 20. A inspeção anterior identificou o emissor RNP ICPEdu GR46 OV TLS CA 2025 e não concluiu uma cadeia até uma raiz confiável. A hipótese de intermediário ausente precisa ser comprovada, não confundida com DNS ou indisponibilidade do dataset.
A DETIC/Unicamp publica esse intermediário em https://www.detic.unicamp.br/documento/certificados-digitais-das-acs/ . Ele não será confiado como raiz: qualquer complemento precisa validar até as raízes já distribuídas, manter hostname, validade e assinaturas e recusar cadeias parciais. Não desabilitar TLS, instalar raiz nova, usar HTTP, substituir fonte/ano ou recorrer a mirror não verificado.

## Aceite e sequência

- [x] E01 Conferir main, AGENTS, TODO e snapshot atual; preservar grupos, OCR e release já concluídos.
- [ ] E02 Reproduzir a verificação de cadeia; implementar complemento restrito ao host oficial, somente se a cadeia for verificável por raízes existentes.
- [ ] E03 Criar regressões reais de handshake: cadeia incompleta/completa, raiz não confiável, hostname errado, expirado, complemento adulterado e ausência de trust global.
- [ ] E04 Executar coleta 2025 com TLS verificado e limites existentes; separar falha da fonte de erro do importador.
- [ ] E05 Processar apenas tabelas escolares; reconciliar contagens/UF, preservar fonte/bytes e validar API e interface com dados reais quando a coleta concluir.
- [ ] E06 Publicar código e executar Quality, runtime e coleta oficial; preservar todos os doze percursos de navegador e piso 85%.
- [ ] E07 Atualizar TODO, ROADMAP, STATUS e evidências com resultado observado, mantendo abertos os requisitos não executados.

## Escopo não encerrado automaticamente

Uma coleta bem-sucedida não certifica disponibilidade de atendimento, todas as geometrias, operação pública, OCR oficial, demais módulos financeiros ou todos os requisitos do roadmap. Não haverá dados fictícios no catálogo público. O relatório deve distinguir implementação, teste, coleta, distribuição e deploy.
