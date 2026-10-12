"""Regras financeiras do Sentavos, num lugar só.

As rotas validam, autorizam, chamam daqui e serializam; o front formata. Cada
regra tem UMA casa — ver docs/financial-domain.md para a matriz de fontes de
verdade e as invariantes.

  - `caixa`: o que sai e entra da conta (cartão sai na fatura; aporte é saída,
    resgate é entrada; nenhum dos dois é gasto ou receita).
  - `contas`: saldo de conta = último saldo observado + movimentos conhecidos
    depois dele, com a qualidade do número (reconciliado, calculado,
    desatualizado, sem saldo).
  - `auditoria`: o rastro das mudanças financeiras fora do fluxo comum.

Os módulos que já eram regra pura continuam onde estão: `app/faturas.py`
(fatura), `app/planejamento.py` (futuro), `app/relatorios.py` (somas por mês e
categoria), `app/cartao.py` (calendário do cartão), `app/rendimento.py` (CDI).
"""
