# Checklist de lançamento comercial web

- [ ] Confirmar que o projeto Railway de staging é isolado, com volume,
  backup testado, domínio HTTPS, alertas de disponibilidade e orçamento de IA.
- [ ] Executar em staging o roteiro de aceitação da documentação. Anexar
  evidências de entrega via Resend, Gemini real com fotos autorizadas, Stripe em
  sandbox e testes no Android e Safari iOS físicos.
- [ ] Revisar termos, política de privacidade e exercício de direitos do
  titular com o responsável pelo produto. Publicar contato monitorado,
  política de retenção e descarte de backups e instruções de exclusão
  assistida para contas com cobrança. Validar obrigações aplicáveis por país.
- [ ] Formalizar o atendimento para reversão, estorno, cancelamento,
  inadimplência, disputas e exclusão em contas ligadas a pagamentos.
- [ ] Validar segregação de contas e uso por função. Operadores com e-mail
  confirmado, recuperação testada e plano para MFA antes da operação
  comercial. Revisar registros administrativos e risco de abuso.
- [ ] Revisar idiomas, moedas, cobrança fiscal, catálogo Stripe, consentimento,
  estados de assinatura, limites mensais, mensagens de erro e fluxo de suporte.
- [ ] Confirmar acesso de escrita na branch de desenvolvimento, revisão de
  código, testes completos, licença GPLv3 e atribuições preservadas.
- [ ] Fazer backup da produção e ensaiar migração e rollback usando um
  ambiente separado antes de agendar qualquer lançamento.
- [ ] Obter aprovação explícita para habilitar cobrança real. O código atual
  restringe o Stripe ao modo de teste. A ativação comercial exige revisão
  e uma alteração posterior para suportar e separar eventos e credenciais live.
- [ ] Para vendas no Android e no iOS, implementar e validar Google Play
  Billing e Apple In-App Purchase antes da distribuição comercial nas lojas.
