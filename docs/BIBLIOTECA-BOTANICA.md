# Biblioteca botânica global

A biblioteca contém 23 espécies. As fichas e as 12 fotografias atribuídas
são entregues com o aplicativo. Uma conta nova pode pesquisar e salvar
espécies sem identificar uma planta antes. Os favoritos da biblioteca são
privados, separados dos favoritos das fichas pessoais e excluídos pelo banco
quando a conta é apagada.

## Fontes e direitos de uso

- **NC State Extension Gardener Plant Toolbox** é a fonte principal para
  taxonomia, cultivo, usos e riscos. Os campos são resumos factuais vinculados
  às fichas da fonte. A biblioteca não replica as páginas de terceiros.
- **GBIF Backbone Taxonomy** documenta a identificação taxonômica da
  [palma-forrageira](https://www.gbif.org/species/5384064).
- **ASPCA Poison Control**, **NIH/NCCIH**, **Embrapa** e **U.S. Fish &
  Wildlife Service** complementam as fichas com evidências sobre toxicidade,
  usos tradicionais, PANCs e conservação. Algumas referências de toxicidade
  veterinária abrangem um gênero. A ficha aponta para a fonte original.
- Os rótulos de busca mesclam nomes editoriais e rótulos do **Wikidata**
  disponíveis sob CC0. Há nomes que coincidem com a denominação científica
  ou recorrem a outro idioma quando o nome vernáculo está indisponível.
- As fotos do **Wikimedia Commons** mantêm autoria, página do arquivo e o
  link da licença individual. Cada foto conserva a sua licença CC BY, CC BY-SA
  ou indicação de domínio público. Consulte os metadados de cada arquivo em
  `plantia/data/botanical_catalog.json`.

## Limites e manutenção

A biblioteca é uma edição versionada. Novas espécies, dados e imagens passam
por revisão antes de entrar. O catálogo global abre sem chamadas ao Gemini ou
às fontes externas. Nas fichas pessoais, as sugestões da identificação
fotográfica continuam visivelmente separadas das evidências botânicas.
Campos sem fonte suficiente ficam como desconhecidos. As fichas têm
cobertura desigual de cultivo, toxicidade e contraindicações. As informações
de uso alimentar registram a evidência disponível e não garantem a segurança
de um exemplar identificado por foto.

A web abre o catálogo em `/enciclopedia` e mantém as fichas do usuário em
`/enciclopedia/pessoal`. O Android usa os mesmos dados em `/api/biblioteca`.
A API `/api/enciclopedia` e os identificadores de fichas pessoais continuam
disponíveis. O PWA usa a política existente de navegação online e página
offline genérica.
