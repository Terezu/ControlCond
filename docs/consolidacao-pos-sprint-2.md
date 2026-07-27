# Consolidação técnica pós-Sprint 2

## Histórico financeiro

O histórico de faturas é representado por
`faturas.HistoricoFinanceiroFatura`. A tabela física continua sendo
`historico_status_faturas` para preservar integralmente os dados existentes e
permitir a evolução de bancos que já aplicaram as migrations anteriores.

A migration `faturas.0017` usa `RenameModel`; não copia, recria ou converte
registros. O relacionamento reverso da fatura é `historico_financeiro` e o
relacionamento do usuário é `alteracoes_financeiras_faturas`.

Novos registros devem ser criados exclusivamente pelos services de faturas,
dentro da mesma transação da operação auditada.

## Índices

O índice `fatura_comp_status_venc_idx` cobre o principal padrão de leitura do
dashboard e da listagem:

1. competência (`ano`, `mes`);
2. situação (`status`);
3. comparação ou ordenação por `data_vencimento`.

Não foram adicionados índices para `data_pagamento`, porque atualmente não há
consulta operacional filtrando por período efetivo de pagamento. O histórico
também não recebeu índice composto: a chave estrangeira `fatura_id` já é
indexada e cada fatura possui poucos eventos.

Antes de criar novos índices, confirmar o padrão com consultas reais e
`QuerySet.explain()`.

## Regressão visual do PDF

`faturas/test_pdf_visual.py` gera faturas determinísticas nos estados pendente
e paga e captura os comandos gráficos emitidos ao ReportLab. Textos e dados
variáveis são descartados; o snapshot protege:

- coordenadas;
- dimensões dos blocos;
- alinhamentos à esquerda e à direita;
- fontes e tamanhos;
- linhas, bordas e cores;
- quantidade e ordem dos comandos visuais.

As assinaturas aprovadas ficam em
`faturas/test_snapshots/pdf_layout.json`. Um snapshot só deve ser atualizado
após revisão visual explícita de uma mudança intencional no PDF.

## Preparação para crescimento

### Paginação do histórico financeiro

Ainda não é necessária. Quando uma fatura puder acumular dezenas de eventos:

1. paginar `fatura.historico_financeiro` em `detalhes_fatura`;
2. preservar `select_related("usuario")`;
3. trocar o contexto por um `Page`;
4. reutilizar o componente de paginação já empregado nas listagens.

### PDFs e ZIPs assíncronos

O volume atual não justifica fila ou armazenamento temporário. Se a geração
passar a exceder o tempo aceitável de requisição:

1. manter `gerar_pdf_fatura_bytes` como unidade síncrona reutilizável;
2. extrair a montagem do ZIP da view `baixar_faturas_mes` para um service;
3. introduzir um modelo de lote com condomínio, competência, usuário, status,
   arquivo, erro e timestamps;
4. enviar somente o identificador do lote para o worker;
5. revalidar condomínio e permissões antes de disponibilizar o arquivo;
6. definir expiração e limpeza dos artefatos;
7. tornar a tarefa idempotente para evitar lotes duplicados.

Uma fila só deve ser escolhida após existir infraestrutura operacional para
worker, retentativas, monitoramento e armazenamento dos arquivos.

## Decisões da auditoria

- O cálculo financeiro permanece em `faturas.services`.
- O dashboard mantém suas agregações em `dashboard.services`.
- A geração visual permanece em `faturas.pdf`.
- Não foi adicionado cache financeiro por não haver uma estratégia segura de
  invalidação que traga benefício no volume atual.
- `faturas.services` é extenso, mas sua divisão agora aumentaria o risco sem
  reduzir duplicação funcional. Uma separação futura deve seguir casos de uso
  (emissão, pagamento, fechamento e consulta), com testes preservados antes da
  movimentação.
- Services globais legados ainda cobertos por testes não foram removidos para
  evitar quebra de integrações internas.
