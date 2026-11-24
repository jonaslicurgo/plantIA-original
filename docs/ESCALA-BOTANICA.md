# Índice botânico internacional

O aplicativo reúne dois tipos de ficha. As 23 fichas revisadas preservam as
referências de cultivo, usos, riscos e evidência. A edição GBIF importa
registros taxonômicos aceitos de **Plantae**, com classificação e sinônimos.
A busca por categorias de uso continua baseada nas fichas com evidências.

## Origem, licenças e cobertura

- [GBIF Backbone Taxonomy](https://doi.org/10.15468/39omei), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
  Esse é o arquivo simplificado que o GBIF publica em `backbone/current`.
  A listagem do servidor data o snapshot consultado em agosto de 2023.
  IDs, nomes, família e hierarquia são indexados; a fonte original segue na ficha.
- O índice local suporta prefixos de nomes científicos e sinônimos via SQLite FTS5.
  Para nomes populares sem correspondência local, a API Taxon do GBIF é consultada
  e suas respostas recebem cache. Os nomes disponíveis dependem do idioma e
  da fonte. As fichas revisadas mantêm os rótulos do Wikidata e o índice próprio.
- A distribuição é apresentada como países com ocorrências registradas no GBIF.
  Presença observada pode incluir introduções e cultivos. A ficha indica isso e
  fornece a busca de ocorrências como fonte. Esses agregados não são mapas de área nativa.
- Imagens vêm de registros de ocorrência e preservam autor, link do registro e
  licença do arquivo. São aceitas apenas licenças CC BY, CC BY-SA e CC0 de mídias
  HTTPS atribuídas, em hosts de imagem aprovados. A licença da ocorrência sozinha
  não basta. O aplicativo não baixa nem redistribui essas imagens no Railway.
  Fotografias já revisadas do Wikimedia Commons seguem com sua atribuição original.
- Características, cultivo, usos, contraindicações e toxicidade têm cobertura
  maior nas fichas revisadas pela NC State Extension, ASPCA, NIH/NCCIH, Embrapa e
  demais fontes documentadas. Ausência de dado fica explícita. Catalogue of Life
  Extended Release fica como uma futura possível fonte de atualização e exige
  mapeamento de taxonomia e verificação dos termos da edição empregada.

O botão Gemini usa a permissão de assistente vigente. O modelo seleciona
chaves entre fatos citados e a aplicação renderiza os valores e fontes já
existentes. O resultado é destacado como seleção feita com IA. A aplicação
não publica texto factual novo gerado pelo modelo nem pede julgamento sobre
consumo ou tratamento. O cache usa espécie, idioma, modelo e versão dos fatos
por 30 dias. Cache de taxonomia e ocorrências é atualizado após sete dias,
buscas de nomes após um dia e indisponibilidade após 15 minutos.

## Railway de staging

O índice SQLite independente é lido em modo somente leitura e o importador o
substitui de forma atômica após verificar integridade e pelo menos 100 mil
espécies. O banco de contas e o diretório de uploads seguem na estrutura anterior.
Uma atualização usa o disco para manter temporariamente duas gerações do índice.
O download gzip de aproximadamente 489 MB é lido em fluxo, sem ser armazenado.

Reserve **1 GB livre** no volume além dos dados existentes. O importador exige
pelo menos 400 MB disponíveis ao iniciar. Para uma réplica, comece com limite de
**512 MiB de RAM**, observe o pico do aplicativo e do importador e meça a carga real
antes de confirmar o dimensionamento.

- Para atualizar automaticamente, configure `PLANET_BOTANICAL_REFRESH_HOURS=168`
  no serviço staging com o volume montado. O launcher verifica a fonte ao iniciar
  e a cada sete dias; ETag igual mantém o snapshot vigente. Em caso de falha,
  o índice anterior continua acessível e a próxima tentativa ocorre em uma hora.
- Para importar manualmente no shell do serviço, use
  `python -m scripts.import_botanical_backbone --output /data/botanical.sqlite`.
  Opcionalmente, `PLANET_BOTANICAL_INDEX` aponta para um arquivo diferente no
  próprio volume. O prazo de atualização é controlado pelo staging.
- O PWA segue com página offline pública. A biblioteca requer conexão. O Android
  usa os mesmos endpoints e não precisa carregar o índice SQLite no aparelho.

## Medição e estimativa

A primeira importação real produziu **444.376 registros adicionais de espécies**,
**675.438 entradas de sinônimos** e um arquivo de **212.664.320 bytes**.
A API soma os registros às 23 fichas revisadas e apresenta **444.399 fichas
pesquisáveis**. A atualização continua útil para versões futuras da mesma fonte,
mesmo que o GBIF mantenha o snapshot atual sem alteração.

A referência pública do Railway indica US$ 10/GB-mês de RAM, US$ 20/vCPU-mês,
US$ 0,15/GB-mês de volume e US$ 0,05/GB de saída. O índice de 0,213 GB equivale a
aproximadamente **US$ 0,03/mês de volume**. Um cenário ilustrativo com média de
0,25 GB de RAM, 0,05 vCPU, 1 GB ocupado no volume e 1 GB de saída equivale a
**US$ 3,70/mês de recursos**. O mínimo do plano Hobby é US$ 5/mês com uso
incluído até esse valor. A conta real depende de carga, fotos servidas pelo
PLANET-IA, backups e outros serviços. Gemini é cobrado separadamente pelo
provedor. As chamadas sob demanda são medidas pelo medidor de consumo existente.

Picos locais de RSS medidos no ensaio: 48,75 MiB no importador e cerca de
118 MiB no processo do aplicativo com consultas reais. São medições de uma
execução local, sem carga concorrente, e não incluem o cache de páginas do SO.

Fonte de tarifas: [Railway Pricing](https://docs.railway.com/reference/pricing).
