# Enriquecimento botânico e implantação em staging

## Fontes e identificação

- [GBIF Taxon](https://techdocs.gbif.org/en/openapi/v1/species) identifica espécies aceitas e sinônimos. O [registro de nomes do GBIF](https://api.gbif.org/v1/species/2868241/vernacularNames?limit=100) atribui **Costela-de-adão** ao Catalogue of Life.
- [World Checklist of Vascular Plants](https://doi.org/10.15468/6h8ucr), CC BY 4.0, fornece forma de vida, bioma e distribuição nativa e introduzida via [Plants of the World Online](https://powo.science.kew.org/). A consulta exige espécie aceita, nome exato, família quando conhecida, correspondência única, identificador IPNI e fonte WCVP no resultado detalhado. Apenas atributos estruturados entram no catálogo.
- [NC State Extension Gardener Plant Toolbox](https://plants.ces.ncsu.edu/) fornece classes de luz, drenagem, umidade, solo, propagação e polinizadores. O adaptador verifica o nome científico da página e converte apenas categorias factuais enumeradas em termos locais. Avisos selecionados de toxicidade, pragas, doenças e rega são resumos editoriais curtos com referências. Páginas, prosa extensa e imagens da Extension ficam fora da integração.
- [ASPCA Poison Control](https://www.aspca.org/pet-care/aspca-poison-control/toxic-and-non-toxic-plants) fundamenta alertas para cães e gatos. A classificação para manjericão é específica para esses animais. NIH/NCCIH, Embrapa e as atribuições das fotos revisadas permanecem na biblioteca.

O aplicativo limita requisições a uma por segundo por host, com quatro segundos de timeout por conexão e tamanho limitado de resposta. São controles locais. As fontes públicas podem mudar seus endpoints e não há SLA acordado. Cada campo documentado exibe sua fonte. As lacunas são reunidas em uma seção com um aviso de que ausência de dados não indica segurança.

## Cache, IA e dimensionamento

O cache SQLite existente é compartilhado entre contas e idiomas. Os fatos públicos expiram em 30 dias. Indisponibilidade é reavaliada após 15 minutos. Uma ficha sem cache faz até duas requisições ao Kew e uma à NC State, além do enriquecimento GBIF já existente. A biblioteca não dispara consultas em massa sobre os 444 mil registros.

Gemini seleciona destaques a partir dos valores e referências já documentados. Os valores exibidos são os originais ou os de glossários e catálogos traduzidos. O modelo não publica afirmações livres nem traduz automaticamente alertas de saúde. Segurança alimentar, toxicidade e medicina não entram na seleção. A abertura de ficha faz zero chamadas ao Gemini. Uma solicitação nova elegível usa no máximo uma tentativa ao modelo com medição e cache de 30 dias por espécie, idioma, versão dos fatos e modelo. O custo depende dos tokens faturados.

O índice de aproximadamente 203 MiB permanece intacto. O teto de cache compartilhado é de 20 mil entradas de até 8 KiB, cerca de 156 MiB de carga útil, mais estruturas SQLite. A US$ 0,15 por GB-mês, cerca de 0,164 GB custaria aproximadamente US$ 0,025 por mês de volume para essa carga útil, antes do overhead. CPU, egress e Gemini dependem do uso. [Tarifas Railway](https://docs.railway.com/reference/pricing)

## Implantação no staging

1. Use a branch planet-ia-desenvolvimento e o volume com /data/botanical.sqlite e plantia.db. Preserve Stripe, Resend e Gemini existentes. O enriquecimento reutiliza o cache e dispensa reimportação.
2. PLANET_BOTANICAL_ENRICHMENT=1 é o padrão. Use 0 para suspender as consultas novas ao Kew e à Extension. As evidências revisadas continuam acessíveis.
3. Opcionalmente, configure PLANET_BOTANICAL_EVIDENCE_REFRESH_HOURS=168. O launcher verifica o cache das cinco espécies prioritárias semanalmente. As outras espécies são revalidadas sob demanda. Para uma verificação manual, execute python -m scripts.refresh_botanical_evidence no serviço.
4. Abra as cinco fichas prioritárias e confira os avisos, a seção de lacunas e as fontes. Para validar Gemini real, use a chave e o modelo já configurados no staging e confira a medição da chamada.

A cobertura de cultivo, toxicidade, alimentação, medicina, cosméticos, alergias e contraindicações varia por espécie. A automação amplia sobretudo taxonomia, distribuição e horticultura. Alguns nomes científicos, topônimos e termos do WCVP são exibidos como publicados pela fonte.

## Pendências após a revisão visual das fichas web e PWA

- Ampliar a cobertura de fontes científicas, verificando a procedência e a licença de cada fonte.
- Enriquecer o conteúdo botânico das fichas com evidências por espécie e referências por informação.
- Atualizar a interface Android nativa para acompanhar a apresentação das fichas web e PWA.
