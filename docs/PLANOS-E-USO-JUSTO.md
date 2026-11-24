# Planos e uso justo de IA

| Plano | BR mensal | BR anual | Consultas de IA | Benefícios padrão de IA |
|---|---:|---:|---|---|
| Gratuito | — | — | 3 por mês | Identificação |
| Plus | R$ 19,90 | R$ 149,90 | 50 por mês, com créditos extras quando concedidos | Identificação e diagnóstico |
| Premium | R$ 29,90 | R$ 199,90 | Sem franquia mensal, sujeito a uso justo | Identificação, diagnóstico e assistente |

Biblioteca, jardim, histórico e acompanhamento manual continuam disponíveis.
O servidor controla a permissão também em chamadas diretas à API.
O painel pode habilitar ou desabilitar recursos, alterar os limites do
Gratuito e Plus e configurar preços e disponibilidade por mercado. Alterações
e créditos concedidos entram na trilha de auditoria.

## Contagem, créditos e proteção

O mês vira às 00:00 UTC no primeiro dia. A mudança de plano no mesmo mês
conserva o consumo já registrado. Resultados em cache não debitam nova
consulta. A tentativa entra na franquia quando reservada e permanece no
consumo se houver falha posterior. Uma nova consulta pode envolver mais de
uma chamada ao Gemini. O painel diferencia operações, tentativas ao
provedor, modelo, tokens reportados e custo estimado em BRL.

Administradores podem conceder créditos a contas Plus elegíveis. O saldo é
usado após a franquia mensal, não expira nesta implementação e fica
indisponível enquanto a conta não for Plus ou o recurso estiver desativado.
A compra de créditos ainda depende de um produto e de um fluxo de pagamento
próprios. Nenhuma compra de créditos é oferecida.

Premium não tem teto mensal. A proteção para uso pessoal admite uma consulta
de IA em andamento por conta, até 15 envios de identificação por hora e até
10 novas operações de diagnóstico e assistente somadas por hora. A proteção
de disponibilidade compartilhada aceita até 120 solicitações de IA por hora
no serviço. Esses controles são limites de cadência, separados dos limites
mensais. Automação em massa pode provocar suspensão da conta. Consultas
interrompidas deixam de ocupar o controle de concorrência após dois minutos.

## Stripe em homologação

1. Use o Stripe em modo de teste e confirme as quatro ofertas recorrentes
   brasileiras com as moedas, ciclos e valores da tabela.
2. Em Administração comercial, associe os quatro IDs de preço. As ofertas
   Premium existentes conservam IDs internos e mapeamentos de preço. Crie
   ofertas internacionais apenas quando houver valores aprovados.
3. Habilite os produtos e as trocas de plano no Customer Portal de teste.
   Assinantes ativos usam o Portal para trocar de plano. A vigência e o
   acesso são atualizados a partir do webhook assinado e do estado retornado
   pela API Stripe. Configure o comportamento de prorrateio no Portal.
4. Valide Checkout, Portal, renovação e eventos no staging. O servidor
   continua recusando credenciais e eventos de produção.
