import ComingSoon from "../components/ComingSoon";

export default function Assets() {
  return (
    <>
      <div className="page-head">
        <div>
          <div className="eyebrow">Estoque</div>
          <h1>Patrimônio</h1>
          <p>Tudo que você tem, menos tudo que você deve.</p>
        </div>
      </div>

      <ComingSoon emoji="🏦" title="Próxima etapa">
        Aqui entram os <b>ativos</b> — conta, renda fixa, renda variável, cripto, imóvel,
        veículo — e as <b>dívidas</b>, com o valor de cada um lançado mês a mês pra formar o
        patrimônio líquido. Ainda não tem backend: falta o modelo de ativo e o registro
        mensal de saldo.
      </ComingSoon>
    </>
  );
}
