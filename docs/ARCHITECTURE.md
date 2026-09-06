<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Arquitetura implementada

A aplicação web não depende de LLM nem usa requisições de usuário para importar dados. Python prepara registros; SQLAlchemy armazena; FastAPI consulta e recebe contribuições; React explora mapa/lista e páginas de evidência. A primeira versão é monólito modular com CLI, não microserviços.

## Entidades e invariantes

Município (IBGE7) → lugar institucional (ID namespaced) → versões. Fonte contém dataset, chave, URL, data de referência, coleta com timezone e SHA-256 dos bytes. Latitude/longitude são ambas nulas ou possuem origem. Código de município6 só é convertido pelo crosswalk derivado dos municípios7 efetivamente carregados. CNPJ alfanumérico conserva letras e zeros; normalização não certifica registro/checksum.

Eventos financeiros conservam instrumento, fase, natureza, período, destinatário, esfera/perspectiva e fonte. Transações de fontes diferentes não se somam automaticamente. Estimativa/cumulativo não se acumulam entre IDs. Correção de valor exige reconciliação explícita; a versão anterior não é silenciosamente sobrescrita. Vínculo com lugar exige evidência e estado direct/reviewed; territorial não admite facility_id.

Identidade institucional e endereço não são equivalentes. Não há vínculo por proximidade/nome. O normalizador PNCP gera metadados sem coordenadas ou escola inventada. Uma obra pode ser importada no formato normalizado, com fonte e município conhecidos.

## Importação

CLI de operador → arquivo preservado → hash → perfil revisado → transação por arquivo → métricas e histórico. Uma linha inválida reverte o arquivo; o registro de falha permanece. Duplicidade de ID no arquivo falha. Reimportação idêntica não duplica histórico. Coleta/hash novos não geram falso evento de mudança. Ineligibilidade explícita retira o lugar da busca, mantendo histórico e ficha; ausência de um ID num arquivo parcial NÃO implica fechamento. Fonte nova não certifica retrospectivamente todo o cadastro.

A versão atual não implementa troca atômica de TODAS as partições nacionais; implementa transação por arquivo. Nacionalidade deve ser verificada com manifestos e reconciliação das partições. Até isso existir, /api/coverage retorna national_catalog_certified=false.

## Documentos

PDF local (32MiB/100p por chamada padrão) → pdfplumber → texto/posições/tabelas → candidatos com offsets. Página sem texto útil ou imagem dominante é encaminhada para revisão/OCR, não automaticamente classificada como documento em branco. Candidatos permanecem publication_allowed=false. Não há extração universal de contratos: quatro padrões iniciais, expansíveis por famílias documentais com corpus de avaliação.

OCR é explícito, uma página, Poppler/Tesseract com por e timeout. Não modifica o original nem valida assinatura. Rodar fora do serviço web com rede desligada, sem credenciais e com recursos limitados. Carga nativa, OCR e significado administrativo são avaliações separadas. Interface de revisão documental, tabelas multipágina e extração de aditivos ainda são backlog.

## Colaboração

Conta com senha scrypt → cookie opaco HttpOnly/SameSite → observação pendente → revisão por outra pessoa → publicação na ficha. Rejeitada e pendente visíveis apenas ao autor/revisores; identidade de autor não é publicada. Registro oficial nunca é editado pelo relato. Sem foto/GPS do cidadão nessa entrega. Ainda faltam exclusão de conta, recursos de apelação, revisão/retração posterior e processos operacionais antes de escala pública.

## Mapa/3D

Mapa carrega somente após consentimento para conexão ao provedor. MapLibre usa GeoJSON da página de resultados, clusters e alturas publicadas da camada building. Zoom >=15 para extrusão; não cria alturas aleatórias. Modelos volumétricos não certificam fachadas ou condições atuais. Lista segue independente de WebGL, GPS ou tiles. Paginação/viewport são limites declarados; vector tiles nacionais, terreno, modelos de obras e Panoramax estão no roadmap.

## Deploy e banco

SQLite para desenvolvimento/single-instance; PostgreSQL para concorrência. create_all + schema_version=1 é bootstrap, NÃO substitui migrações evolutivas. Antes da segunda versão estrutural, introduzir Alembic e testar upgrades/restores. API não deve reiniciar migration DDL concorrente numa implantação multi-replica. A aplicação começa sem registros.
