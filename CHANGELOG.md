# Changelog

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

Use `PLANET_STAGING_GEMINI_API_KEY` para uma chave própria de homologação. A chave é opcional para navegar. A recuperação real requer `PLANET_STAGING_SMTP_HOST`, `PLANET_STAGING_SMTP_FROM` e, quando aplicável, usuário e senha dedicados. O servidor retorna indisponível sem SMTP configurado. Use a página web para cadastro e recuperação; no Android atualizado, configure o endereço HTTPS e entre em Ajustes. O app mantém o token de sessão em memória, usa a mesma API de plantas e mantém lembretes locais separados por conta e servidor. Clientes antigos sem login recebem 401 nos endpoints privados.

A migração SQLite é aditiva e deve ser executada primeiro sobre uma cópia dos dados, com backup consistente do banco e das fotos. Os registros antigos recebem proprietário nulo; só faça uma atribuição depois de verificar a correspondência de usuários e registros fora da interface pública. Mantenha o banco e as fotos no mesmo volume persistente e use uma instância SQLite. Para reverter, restaure a cópia pré-migração em isolamento, pois o servidor original não aplica a autorização por conta.

## Regressão

Instale `httpx` no ambiente de testes e execute `python -B -m unittest discover -s tests -v`. Os testes usam banco temporário, duas contas, Gemini simulado e entrega SMTP simulada. Validação linguística humana, entrega SMTP real e identificação real com chave de homologação permanecem etapas de aceitação. Alguns textos nativos dinâmicos, como os nomes das fases da Lua, ainda usam o espanhol original. O cadastro ainda não exige confirmação do endereço de e-mail.

Foto da abertura: [Unsplash](https://images.unsplash.com/photo-1485955900006-10f4d324d411), usada sob a [licença Unsplash](https://unsplash.com/license).
