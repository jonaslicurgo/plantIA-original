# Changelog

## Envio de e-mails via Resend

- Verificação de cadastro, reenvio e recuperação usam o Resend via HTTPS. Mantidos os códigos de uso único, a expiração e os limites. Staging requer `PLANET_RESEND_API_KEY` e `PLANET_RESEND_FROM`.

## Homologação, PWA e privacidade

- Configuração Railway separada com volume para SQLite e fotos, HTTPS e verificação de prontidão. Gemini, Stripe de teste e SMTP são configurados no ambiente.
- PWA com instalação, ícones, tela de abertura e página offline pública. Páginas de conta e dados privados dependem da rede.
- Verificação de e-mail com código de uso único e confirmação de senha, exclusão de contas sem vínculo de cobrança ou função administrativa, página de privacidade e proteção de privilégios em homologação.
- Android de depuração com identificador separado, servidor configurável por HTTPS e teste de conexão. Atualizados os roteiros de testes, implantação e lançamento.

## Assinaturas, consumo de IA e administração

- Planos Gratuito, Premium Mensal e Premium Anual com catálogo por mercado, moeda e ciclo. Os valores iniciais para o Brasil são R$ 29,90 por mês e R$ 199,90 por ano. Preços, disponibilidade, franquias e estimativas de custo são configuráveis no painel.
- Stripe Checkout e Customer Portal em modo de teste. Webhooks assinados reconciliam o estado da assinatura com o Stripe, registram alterações e descartam repetições. A franquia Premium acompanha a vigência registrada no servidor.
- Medição de identificação e diagnóstico por conta e operação, com limites mensais em UTC, estimativa de custo e captura de tokens quando o Gemini fornece os dados. Resultados reutilizados dispensam nova reserva. A franquia restante aparece na web e no Android.
- Painel web com usuários, assinaturas, receita recorrente por moeda, margem estimada em BRL, erros, consumo e trilha de auditoria. Administradores editam regras e contas. Auditores consultam indicadores e registros.
- Interface web comercial nos 12 idiomas do aplicativo, incluindo RTL em árabe. O Android consulta o estado da assinatura. A estrutura de assinaturas aceita a origem do pagamento e prepara a integração futura com as lojas.

## Jardim Virtual no Android

- Aba Jardim Virtual com filtro de local, perfis dos exemplares, agenda, criação, reagendamento e conclusão de tarefas usando os mesmos registros da web.
- O diagnóstico abre o agendamento de reavaliação com a data selecionada. Os lembretes locais de rega aproveitam a data de conclusão do servidor ao concluir uma rega ou abrir o jardim. Uma conclusão antiga não retrocede o lembrete local.
- A interface acompanha o idioma do aplicativo. O servidor devolve a mesma data em confirmações repetidas, por conta e exemplar.

## Etapa 4 · Jardim Virtual

- Jardim privado na web e na API, com os exemplares já existentes, apelidos, locais de cultivo e filtro por local. As fichas mantêm atalhos para identificação, enciclopédia e saúde do mesmo registro.
- Agenda de rega, adubação, poda, transplante e reavaliação de saúde. Usuários podem agendar, reagendar e concluir cuidados e consultar os cuidados concluídos. As sugestões de reavaliação abrem um formulário preenchido e exigem que o usuário salve o agendamento.
- Migração aditiva, vínculo por exemplar, controle de acesso e exclusão em cascata das tarefas quando a planta é removida. Interface web nos 12 idiomas.

## Etapa 3 · Diagnóstico, recuperação e acompanhamento

- Web e Android oferecem triagem fotográfica com sinais visíveis, hipóteses de doenças fúngicas, bacterianas e virais, pragas e fatores ambientais. O formulário recebe sintomas, rega, luz, local, solo, umidade, temperatura e contexto. Folhas secas, lagartas, problemas de substrato e temperatura têm códigos próprios.
- Avaliações preliminares indicam gravidade visual, ausência de sinais evidentes ou resultado inconclusivo com pedido de novas imagens. Uma confirmação recebida de especialista pode ser registrada pelo usuário em evento separado e é identificada como declaração externa.
- Plano de recuperação com ações conservadoras selecionadas por sinais, hipótese, contexto e gravidade. Inclui inspeção, manejo físico/cultural de baixo risco, prevenção e data sugerida de reavaliação. Orientações e referências são controladas no servidor. O provedor não gera dosagens, produtos, receitas, misturas ou instruções de aplicação.
- Linha do tempo privada por exemplar para várias avaliações, fotos, medidas tomadas, notas e evolução. Comparação das duas últimas avaliações e das duas últimas fotos. A ficha de saúde abre a enciclopédia do mesmo exemplar. O vínculo por ID e os eventos datados permitem integração futura com o jardim.
- Assistente contextual de cuidados vegetais, com perguntas e respostas privadas por exemplar. O Gemini seleciona ações de um catálogo controlado. Perguntas fora do escopo ou com dados insuficientes retornam estados específicos. A foto de avaliação e os dados privados de outra conta não entram nas conversas.
- Cache privado de 24 h por conta, exemplar, operação, contexto e modelo. Solicitações idênticas em andamento são bloqueadas antes de chamar o provedor. Fotos são validadas, normalizadas em JPEG de até 1.440 px e armazenadas com acesso restrito. Mantida a configuração do Gemini no servidor, incluindo `gemini-3.1-flash-lite`.
- Registro de uso de IA por conta e operação, cota horária e fronteira de política para integração futura com assinaturas e créditos. A exclusão do exemplar remove fotos e eventos, enquanto o contador de uso permanece, sem cópia das fotos, notas ou perguntas. Compras e faturamento seguem fora deste módulo.
- Interface, alertas, hipóteses e orientações controladas nos 12 idiomas, incluindo árabe com RTL. As datas de reavaliação são exibidas dentro do aplicativo. A etapa não adiciona notificações push.
- Testes de regressão com Gemini simulado e validação em ambiente isolado. O Android usa o seletor de fotos do sistema. Consulte `RESULTADOS-TESTES.txt` no pacote desta etapa.

## Etapa 2 · Enciclopédia botânica

- Enciclopédia privada na web e no Android, com 31 campos em seis grupos expansíveis, busca por nomes populares ou científicos, filtros de evidência por categoria e favoritos.
- O Gemini sugere a identidade da foto. A ficha consulta o GBIF para taxonomia de espécies aceitas com correspondência exata. A referência taxonômica descreve a espécie e não confirma o exemplar. Resultados duvidosos retornam HTTP 422 com o código `identification_inconclusive`, orientação para novas fotos e nenhum registro ou foto salvo.
- Curadoria inicial para sete espécies com referências por campo. As fontes incluem [NC State Extension](https://plants.ces.ncsu.edu/), [NIH NCCIH](https://www.nccih.nih.gov/health), [ASPCA](https://www.aspca.org/pet-care/aspca-poison-control), [U.S. Fish & Wildlife Service](https://www.fws.gov/species/venus-fly-trap-dionaea-muscipula) e [Embrapa](https://www.infoteca.cnptia.embrapa.br/infoteca/handle/doc/1132694). Usos tradicionais, evidência limitada e lacunas são identificados. A ficha não recomenda ingestão, preparo, tratamento ou dosagem. Os campos legados de toxicidade da API foram mantidos no contrato, com valores vazios. A toxicidade passa a ser exibida na ficha com referências.
- As consultas à enciclopédia não chamam o Gemini. As taxonomias públicas são armazenadas por até sete dias. Buscas válidas sem correspondência ficam em cache por seis horas. Falhas de conexão usam a curadoria e o estado de informação insuficiente. A mesma foto processada na mesma conta, idioma, modelo e versão do prompt reutiliza o registro por 24 horas, enquanto ele e a foto existirem. A exclusão remove também a possibilidade de reutilizá-lo. Fotos, notas, favoritos e identificadores de conta ficam fora do cache público.
- Migração aditiva para favoritos e metadados de cache no SQLite. As rotas autenticadas `/api/enciclopedia` e `/api/enciclopedia/{id}` fornecem a ficha e a busca. `PATCH /api/enciclopedia/{id}/favorito` recebe um booleano JSON `favorite`.
- Os 12 idiomas incluem a interface, os alertas, o estado inconclusivo e o conteúdo curado inicial. A cobertura factual depende das fontes e dos táxons curados. Fichas sem fonte específica marcam os campos correspondentes como insuficientes.

## Etapa 1 · PLANET-IA

- Marca PLANET-IA, slogan, identidade web responsiva e telas de conta.
- Doze catálogos web e recursos Android; detecção de idioma do sistema, escolha manual, persistência, RTL e idioma solicitado ao Gemini. Chaves do JSON da API, nomes taxonômicos e níveis de confiança seguem estáveis.
- Cadastro, login e logout; Argon2id; cookies de sessão HTTP-only ou bearer no Android; tokens aleatórios armazenados como hash; recuperação SMTP com código de uso único, expiração e revogação de sessões.
- Consultas, anotações, exclusões e mídia restritas ao proprietário. Rotas de desligamento e de configuração web desabilitadas. Segredos Gemini somente no ambiente do servidor. Limites por IP, conta e ação, validação de origem para formulários e respostas sem cache compartilhado.
- Limites de upload e validação de imagem, tamanho, MIME e pixels; fotos preparadas sem metadados desnecessários; cálculo e chamadas de IA fora do loop assíncrono. Os identificadores e campos públicos da API para plantas continuam compatíveis com o cliente Android atualizado.
- Diretório de dados configurável, migração aditiva de propriedade e inicialização das tabelas de conta e sessão. Dados legados ficam preservados e inacessíveis até atribuição explícita e auditada por um operador.
- Launcher isolado de homologação e regressão automatizada. GPL v3 e crédito ao projeto original preservados.

## Executar em homologação

Instale `requirements.txt` em um ambiente virtual. Exporte `PLANET_STAGING_DATA_DIR` apontando para um diretório novo ou volume exclusivo. Execute `scripts/homologacao.sh`. O launcher usa a porta 8081 e interface local por padrão. Para teste HTTP local, defina `PLANET_STAGING_INSECURE_LOCAL_HTTP=1`. Para uma homologação HTTPS, deixe o padrão seguro e configure `PLANET_STAGING_PUBLIC_ORIGIN` com a origem HTTPS exata do proxy e a interface de escuta adequada à rede privada. Configure limitação de corpo e taxa também no proxy e só confie em cabeçalhos de encaminhamento de proxies conhecidos.

Use `PLANET_STAGING_GEMINI_API_KEY` para uma chave própria de homologação. A chave é opcional para navegar. No script local de homologação, configure `PLANET_STAGING_RESEND_API_KEY` e `PLANET_STAGING_RESEND_FROM` para enviar e-mails. Use a página web para cadastro e recuperação; no Android atualizado, configure o endereço HTTPS e entre em Ajustes. O app mantém o token de sessão em memória, usa a mesma API de plantas e mantém lembretes locais separados por conta e servidor. Clientes antigos sem login recebem 401 nos endpoints privados.

A migração SQLite é aditiva e deve ser executada primeiro sobre uma cópia dos dados, com backup consistente do banco e das fotos. Os registros antigos recebem proprietário nulo; só faça uma atribuição depois de verificar a correspondência de usuários e registros fora da interface pública. Mantenha o banco e as fotos no mesmo volume persistente e use uma instância SQLite. Para reverter, restaure a cópia pré-migração em isolamento, pois o servidor original não aplica a autorização por conta.

## Regressão

Instale `httpx` no ambiente de testes e execute `python -B -m unittest discover -s tests -v`. Os testes usam banco temporário, duas contas, Gemini simulado e entrega SMTP simulada. Validação linguística humana, entrega SMTP real e identificação real com chave de homologação permanecem etapas de aceitação. Alguns textos nativos dinâmicos, como os nomes das fases da Lua, ainda usam o espanhol original. O cadastro ainda não exige confirmação do endereço de e-mail.

Foto da abertura: [Unsplash](https://images.unsplash.com/photo-1485955900006-10f4d324d411), usada sob a [licença Unsplash](https://unsplash.com/license).
