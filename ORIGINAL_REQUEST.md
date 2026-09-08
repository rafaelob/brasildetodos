# Original User Request

## 2026-09-08T18:25:27Z

# Teamwork Project Prompt — Execução

Plataforma cívica e de transparência Brasil de Todos: expansão integral de dados públicos abertos com ingestão oficial (Obrasgov, Transferegov, Inep), nova identidade visual com logotipo cívico vetorial brasileiro (bandeira e cidadão), interface moderna, fluida e acessível, com segurança e verificação contínua de ponta a ponta.

Working directory: c:\Projetos\BrasilDeTodos
Integrity mode: development

## Requirements

### R1. Ingestão e Indexação de Fontes Oficiais
Construir e consolidar pipelines de importação das fontes oficiais abertas do governo federal (Obrasgov.br projetos e medições, Transferegov.br repasses e convênios, INEP microdados e localização escolar, e CNES estabelecimentos), gravando proveniência explícita (URL real, hash SHA-256 da fonte e data de referência) e garantindo que nenhum slug técnico ou dado fictício chegue à interface do cidadão.

### R2. Nova Identidade Visual e Logotipo Cívico Brasileiro
Criar e integrar um logotipo vetorial moderno e escalável (SVG nativo) que una a brasilidade (cores verde, amarelo e azul, losango e esfera) com o protagonismo do cidadão e o marco cívico, aplicando-o de forma harmoniosa no cabeçalho (desktop e mobile), no favicon e nas telas da aplicação.

### R3. Refinamento de Interface, Fluidez e Acessibilidade Multilíngue
Aprimorar a experiência de uso das telas de exploração, mapas 2D/3D interativos, consulta regional e detalhamento de serviços públicos, assegurando layout solto e espaçoso com conformidade de contraste WCAG, navegação tátil perfeita em smartphones e paridade de tradução entre português (pt-BR), inglês (en) e espanhol (es).

### R4. Segurança, Moderação e Integridade de Operação
Garantir validação e sanitização estrita de entradas em contribuições cidadãs, proteção CSRF, moderação de publicações e conformidade com as regras de engenharia da plataforma (zero dependência de LLM ou bancos vetoriais em tempo de execução, zero vazamento de segredos).

## Acceptance Criteria

### Proveniência e Dados Oficiais
- [ ] Todas as novas cargas de dados preservam registro de proveniência com hash SHA-256 e URL válida da fonte pública.
- [ ] Nenhuma string técnica (ex.: `cnes-national-bulk`, slugs crus) ou texto `"Não informado"` em dados oficiais é exibido no lugar de rótulos humanizados e `"Cadastro oficial"`.
- [ ] A suíte de testes do backend (`pytest`) executa e passa 100% verde sem regressões.

### Logotipo e Identidade Visual
- [ ] Logotipo vetorial em SVG responsivo implementado com as cores e formas do Brasil integradas à figura cívica do cidadão.
- [ ] O logotipo renderiza perfeitamente no cabeçalho em telas de grande escala (desktop 1440px+) e telas móveis (375px-430px), além de atualizar o favicon.

### Interface, Usabilidade e Acessibilidade
- [ ] O mapa e a lista de serviços abrem de forma imediata e fluida, sem barras de rolagem duplicadas ou cabeçalhos sobrepostos.
- [ ] Os testes unitários e de internacionalização do frontend (`npm test`) e o build de produção (`npm run build`) concluem com 100% de sucesso.
- [ ] Todas as novas strings da interface possuem tradução equivalente e completa em `pt-BR`, `en` e `es`.

### Verificação em Ambiente Integrado
- [ ] O ambiente integrado no Docker Compose inicia saudavelmente e todos os endpoints respondem com sucesso em `http://127.0.0.1:8008`.
