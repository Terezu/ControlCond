# Roteiro de testes externos — ControlCond

Use somente informações fictícias. Marque cada item com `[x]`, registre
“Não aplicável” quando necessário e anexe evidências sem dados reais.

## Identificação do ambiente

- Sistema operacional e versão:
- Python (`python --version`):
- Navegador e versão:
- Resolução da tela:
- Data e hora do teste:
- Branch e commit (`git branch --show-current` e `git rev-parse --short HEAD`):
- Nome do tester:

## Instalação

- [ ] Clonar somente `release/teste-externo`.
- [ ] Criar e ativar `.venv`.
- [ ] Atualizar `pip`.
- [ ] Instalar `requirements.txt` sem erro.
- [ ] Copiar `.env.example` para `.env` e trocar a chave local.
- [ ] Executar `python manage.py migrate`.
- [ ] Executar `python manage.py check`.
- [ ] Criar superusuário com dados fictícios.
- [ ] Iniciar o servidor e acessar a página inicial.

## Fluxo inicial

- [ ] Fazer login.
- [ ] Criar um condomínio fictício.
- [ ] Preencher a configuração financeira do condomínio.
- [ ] Definir o condomínio ativo.
- [ ] Confirmar que nome e tema correspondem ao condomínio ativo.

## Multi-condomínio

- [ ] Criar dois condomínios fictícios, A e B.
- [ ] Alternar entre A e B.
- [ ] Confirmar isolamento dos apartamentos.
- [ ] Confirmar isolamento das leituras.
- [ ] Confirmar isolamento das faturas.
- [ ] Confirmar isolamento de configuração financeira e tarifas.
- [ ] Confirmar isolamento do tema e do dashboard.
- [ ] Confirmar que nenhuma URL do condomínio A revela dados no B.
- [ ] Registrar contratos como “Não aplicável”: não há módulo de contratos
      nesta branch.

## Usuários e permissões

Os papéis disponíveis são Proprietário, Administrador, Operador e Somente
consulta.

- [ ] Criar usuários fictícios para os papéis relevantes.
- [ ] Vincular cada usuário somente ao condomínio de teste adequado.
- [ ] Validar ações permitidas para cada papel.
- [ ] Tentar acessar uma ação sem permissão.
- [ ] Tentar acessar diretamente a URL de um dado de outro condomínio.
- [ ] Confirmar redirecionamento ou bloqueio sem vazamento de informação.

## Apartamentos

- [ ] Cadastrar apartamento.
- [ ] Editar os dados.
- [ ] Visualizar detalhes.
- [ ] Usar filtros e paginação, quando disponíveis.
- [ ] Tentar duplicar número/bloco no mesmo condomínio.
- [ ] Validar campos obrigatórios, números negativos e formatos inválidos.
- [ ] Confirmar que o apartamento não aparece no outro condomínio.

## Leituras

- [ ] Criar as leituras-base necessárias.
- [ ] Cadastrar leitura de água e gás.
- [ ] Conferir consumo calculado.
- [ ] Tentar cadastrar leitura duplicada na mesma competência.
- [ ] Tentar leitura inferior à anterior.
- [ ] Tentar valores e competência inconsistentes.
- [ ] Confirmar isolamento entre condomínios.

## Contratos

O módulo de Gestão de Contratos pertence à Sprint 2.5 e não está implementado
nesta branch. Não simular nem validar contratos por campos não equivalentes.

- [ ] Registrar “Não aplicável nesta versão” para cadastro, edição,
      encerramento, vencimento, reajuste, indicadores e integração com aluguel.

## Faturas

- [ ] Gerar fatura individual.
- [ ] Gerar fechamento mensal em lote.
- [ ] Conferir água, gás, aluguel, condomínio, IPTU, descontos e outros.
- [ ] Aplicar desconto válido e rejeitar entrada inválida.
- [ ] Testar bonificação padrão do condomínio.
- [ ] Testar bonificação específica percentual.
- [ ] Testar bonificação específica de valor fixo.
- [ ] Testar opção sem bonificação.
- [ ] Confirmar que a específica substitui, sem somar, a padrão.
- [ ] Gerar PDF individual.
- [ ] Gerar ZIP mensal e conferir apenas arquivos do condomínio ativo.

## Pagamentos

- [ ] Registrar pagamento antes da data-limite de bonificação.
- [ ] Registrar pagamento no vencimento.
- [ ] Registrar pagamento em atraso.
- [ ] Conferir multa.
- [ ] Conferir juros no modo diário.
- [ ] Conferir juros no modo mensal.
- [ ] Conferir bonificação elegível e ausência fora do prazo.
- [ ] Confirmar valor final e status “Paga”.
- [ ] Estornar pagamento com motivo.
- [ ] Reabrir fatura com motivo.
- [ ] Conferir histórico financeiro, usuário, data e snapshots.
- [ ] Confirmar que valores pagos permanecem congelados.

## Dashboard

- [ ] Conferir receitas previstas.
- [ ] Conferir receitas recebidas.
- [ ] Conferir receitas pendentes.
- [ ] Conferir receitas vencidas.
- [ ] Conferir inadimplência.
- [ ] Conferir totais de bonificações, multas e receita líquida.
- [ ] Testar filtros de mês e ano.
- [ ] Alternar condomínio e confirmar atualização e isolamento dos números.

## PDF

- [ ] Conferir identidade visual e hierarquia.
- [ ] Conferir quadro geral.
- [ ] Conferir água/esgoto e gás.
- [ ] Registrar contrato como “Não aplicável nesta versão”.
- [ ] Conferir composição dos valores e alinhamentos.
- [ ] Conferir vencimento e data de pagamento.
- [ ] Conferir origem e valor da bonificação, quando houver.
- [ ] Conferir multa, juros, valor original e valor pago.
- [ ] Conferir que textos longos não quebram valores ou tabela.

## Modelo para relato de defeito

**Título:**  
**Página/URL:**  
**Pré-condições:**  
**Passos para reproduzir:**  
**Resultado esperado:**  
**Resultado obtido:**  
**Evidência (sem dados reais):**  
**Mensagem do console/terminal:**  
**Navegador e versão:**  
**Severidade:**  

Escala:

- **Bloqueador:** impede instalar, iniciar ou concluir um fluxo essencial;
- **Alto:** fluxo importante falha e não há alternativa segura;
- **Médio:** falha parcial com alternativa;
- **Baixo:** impacto pequeno sem perda funcional relevante;
- **Sugestão:** melhoria não associada a defeito funcional.

## Encerramento

- [ ] Executar `python manage.py test` e registrar o resultado.
- [ ] Encerrar o servidor com `Ctrl+C`.
- [ ] Confirmar que `.env`, banco, mídia, PDFs, ZIPs e logs não foram
      adicionados ao Git.
- [ ] Enviar somente o relatório e evidências previamente revisadas.
