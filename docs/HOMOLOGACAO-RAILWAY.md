# Homologação do PLANET-IA no Railway

Use o projeto separado `PLANET-IA Staging`, o ambiente `staging` e um serviço
exclusivo. Mantenha a integração e as configurações do projeto de produção
intactas. Crie as contas de teste diretamente na homologação.

## GitHub e o erro 403

O Git do ambiente usa HTTPS com o helper `gh auth git-credential`. A sessão
`GH_TOKEN` é de `jonaslicurgo`. A API confirma que a conta é administradora do
repositório. O GitHub recusou o push simulado com 403. A instalação do GitHub App
conectada ao Codex é a [183745526](https://github.com/settings/installations/183745526).
Na verificação desta etapa, a lista da instalação continha somente o repositório
`pixel-perfect-match`, e a autorização de escrita no PlantIA precisa ser concedida
à integração.

1. Entre como `jonaslicurgo` na [configuração da instalação](https://github.com/settings/installations/183745526).
2. Em **Repository access**, mantenha **Only select repositories** e acrescente
   `jonaslicurgo/plantIA-original` à seleção. Salve e confirme **Contents: Read
   and write** na seção de permissões. Se a integração apresentar uma solicitação
   oficial para ampliar permissões, revise e aprove a escrita de conteúdo do app.
3. Reconecte o GitHub no Codex ou inicie uma sessão nova para renovar a
   autorização do ambiente. Rode o teste abaixo na cópia local. Confira
   também se existe uma regra para `planet-ia-desenvolvimento` que exija PR
   ou verificações. Preserve as regras de `main` e de backup.
4. Se o App ainda não oferecer escrita, o proprietário pode enviar os commits
   do bundle da sua máquina usando a própria sessão do GitHub CLI
   (`gh auth login --hostname github.com --web`, `gh auth setup-git`).
   Respeite as regras da branch. Mantenha credenciais no fluxo do GitHub.

```sh
git -c credential.helper= -c 'credential.helper=!gh auth git-credential' \
    push --dry-run origin HEAD:refs/heads/planet-ia-desenvolvimento
```

## Serviço, volume e HTTPS

1. Crie um projeto separado no Railway, escolha ou renomeie o ambiente para
   `staging` e crie um serviço novo. Para deploy via GitHub, conecte o PlantIA
   e selecione exclusivamente `planet-ia-desenvolvimento`. A instalação
   Railway GitHub App também precisa de acesso ao repositório selecionado.
   Em **Config as Code**, selecione `ops/staging/railway.toml`. Deixe a raiz
   da aplicação na raiz do repositório.
2. Anexe um volume **novo** no caminho `/data`. O volume contém SQLite em
   `/data/plantia.db` e as fotos em `/data/uploads`. Mantenha uma réplica.
   Configure política de backup do volume no Railway e teste restauração em
   outro volume. Trate backups como dados privados.
3. Em **Networking**, gere um domínio público Railway para este serviço. Use
   o HTTPS emitido pelo Railway e copie o domínio exato em
   `PLANET_PUBLIC_ORIGIN`. A rota `/health` verifica o banco e a pasta de
   uploads. O launcher verifica o ambiente, o caminho do volume, o domínio e
   as configurações de segurança antes de iniciar. A porta é definida pelo
   Railway por meio de `PORT`.
4. Se o GitHub estiver bloqueado, o ZIP restaurado permite ao proprietário
   fazer o primeiro deploy pelo CLI Railway. Configure no serviço o caminho
   do arquivo Config as Code primeiro. Em uma sessão local autenticada no
   Railway, execute `railway link` e selecione o projeto novo, o ambiente
   `staging` e seu serviço. Confira com `railway status` e execute
   `railway up --environment staging --service NOME_DO_SERVICO` na raiz.
   O CLI usa a sessão oficial do operador.

| Variável | Valor |
| --- | --- |
| `PLANET_DEPLOYMENT` | `staging` |
| `PLANET_DATA_DIR` | `/data` |
| `PLANET_PUBLIC_ORIGIN` | Origem HTTPS do serviço, sem barra final |
| `PLANET_REQUIRE_VERIFIED_EMAIL` | `1` |
| `PLANET_PRIVACY_CONTACT` | Caixa pública de suporte para pedidos de privacidade |
| `GEMINI_MODEL` | `gemini-3.1-flash-lite` |
| `GEMINI_API_KEY` | Chave em projeto Google separado, com controle de orçamento e acesso |
| `PLANET_STRIPE_KEY` | Chave `sk_test_` ou `rk_test_` de uma conta de testes |
| `PLANET_STRIPE_WEBHOOK_SECRET` | Segredo do endpoint de teste no Stripe |
| `PLANET_SMTP_HOST`, `PLANET_SMTP_FROM` | Host do provedor e remetente verificado |
| `PLANET_SMTP_USER`, `PLANET_SMTP_PASSWORD` | Credenciais SMTP do ambiente |
| `PLANET_SMTP_SECURITY`, `PLANET_SMTP_PORT` | `ssl` e `465`, ou `starttls` e `587` |

Grave segredos nas variáveis do serviço. Confirme se o plano Railway e o
provedor permitem saída SMTP na porta escolhida. A entrega real precisa ser
testada a partir do serviço. O SMTP usa validação de certificado e autenticação
depois do estabelecimento do TLS. Deixe `PLANET_INSECURE_LOCAL_HTTP` ausente.

## Roteiro de aceitação em homologação

- Confira `/health` em HTTPS. Registre duas contas de QA, confirme a entrega dos
  códigos em caixas autorizadas, verifique acesso, recuperação e expiração de
  código. A verificação usa o código recebido e a senha da conta. Confirme
  que os dados permanecem após reiniciar ou redeployar o serviço.
- Faça uma identificação com foto de planta autorizada, confira o nome, a
  enciclopédia, um diagnóstico com ressalva de incerteza, tarefas do jardim,
  conclusão de rega e o isolamento das duas contas. Confira uso de IA e
  franquias no painel. Use a modelagem e credenciais da tabela acima.
- Para habilitar a operação administrativa, confirme o e-mail da conta de
  operação e use o shell do **serviço de staging** com o volume montado:
  `python -m scripts.commercial_bootstrap ID_DA_CONTA`. Os IDs podem ser
  obtidos de forma privada a partir da sessão API da própria conta de teste.
  Teste acesso de admin, auditor e membro. Confira a revogação de sessão
  ao mudar privilégios no ambiente com verificação obrigatória.
- Cadastre no painel os IDs de preços recorrentes do Stripe em modo de
  teste e habilite o Customer Portal de teste. Configure
  `https://DOMINIO-DE-STAGING/api/stripe/webhook` com os eventos de assinatura
  descritos no README. Use um cartão de teste oficial e verifique alteração
  de plano, renovação, cancelamento, repetição do webhook e franquia.
- Use a página **Privacidade e conta** para testar a exclusão de uma conta
  de QA sem vínculo de cobrança. Para contas com Stripe ou papel operacional,
  utilize o canal de privacidade configurado para revisão manual.
- Abra o site no Chrome Android e no Safari iOS. Use **Instalar app** no
  Chrome, e **Compartilhar → Adicionar à Tela de Início** no Safari.
  Verifique ícone, abertura, formulário, navegação, RTL e tela offline
  genérica em modo avião. O Service Worker guarda somente a página offline.
- Instale o APK de depuração `com.plantia.staging` no Android. Em
  **Configurações**, informe o domínio HTTPS e teste a conexão antes do login.
  Cadastre e verifique o e-mail na web. Teste câmera, galeria, diagnóstico,
  agenda e notificações, inclusive após reiniciar o aparelho. O APK
  distribuído aceita configurar a URL pelo aplicativo. Para compilá-la como
  padrão, use `./gradlew assembleDebug -PplanetStagingOrigin=https://DOMINIO/`
  na pasta `android/PlantIAAndroid`.

## Execução automatizada local

Instale `requirements-test.txt` com pip e execute `python -B -m unittest discover -s tests -v`.
A suíte usa banco temporário. Ela contém jornadas HTTP de conta,
isolamento, identificação, enciclopédia, saúde, agenda, franquia e Stripe
com provedores simulados. Para o teste `tests/pwa_browser.cjs`, use Node e
Playwright com Chromium. Suba um Uvicorn local na porta 8893 com banco
temporário, `PLANET_PUBLIC_ORIGIN=http://127.0.0.1:8893` e
`PLANET_INSECURE_LOCAL_HTTP=1`. Cadastre
`pwa-fixture@example.com` com a senha de fixture definida no teste.
Execute `node tests/pwa_browser.cjs`. Esse teste exercita o Service Worker
num navegador real e exige exclusivamente um servidor em loopback.
