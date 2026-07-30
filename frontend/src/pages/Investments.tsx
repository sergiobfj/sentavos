import ComingSoon from "../components/ComingSoon";

export default function Investments() {
  return (
    <>
      <div className="page-head">
        <div>
          <div className="eyebrow">Carteira</div>
          <h1>Investimento</h1>
          <p>Quanto você já guardou e quanto isso virou.</p>
        </div>
      </div>

      <ComingSoon emoji="📈" title="Próxima etapa">
        Esta aba não vai ter dados próprios: ela é uma <b>visão de Patrimônio</b> filtrada
        pelas classes de investimento, cruzada com os aportes que já vêm dos lançamentos.
        É de propósito — duas telas com números próprios pro mesmo dinheiro é como elas
        começam a divergir. Depende de Patrimônio ficar de pé primeiro.
      </ComingSoon>
    </>
  );
}
