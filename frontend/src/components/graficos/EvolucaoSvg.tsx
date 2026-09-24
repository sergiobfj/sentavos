import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipProps,
} from "recharts";
import { formatMoney } from "../../lib/format";
import { COR_SERIE } from "../../lib/paleta";

export interface PontoEvolucao {
  chave: string;
  rotulo: string; // "set"
  mesLongo: string; // "setembro de 2026"
  // Nulo = mês sem como saber (nenhum gasto com finalidade registrada). Vira
  // um vão na linha, e não um zero que afirmaria "não gastei nada".
  valor: number | null;
  atual: boolean;
}

/** A linha de evolução dos gastos. Mora no chunk do Recharts.
 *
 * Linha e não barra: a pergunta é "estou gastando mais ou menos do que antes",
 * e a inclinação responde isso de relance. Barras mostram doze alturas que o
 * olho precisa comparar uma a uma.
 *
 * Eixo Y escondido: num celular, uma régua com R$ 0 / R$ 1.000 / R$ 2.000
 * come um quinto da largura pra dizer o que o toque no ponto diz melhor. O
 * número exato está no tooltip e no resumo acima do gráfico.
 */
export default function EvolucaoSvg({ pontos }: { pontos: PontoEvolucao[] }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={pontos} margin={{ top: 12, right: 12, bottom: 0, left: 12 }}>
        <CartesianGrid vertical={false} stroke="#242423" />
        <XAxis
          dataKey="rotulo"
          axisLine={false}
          tickLine={false}
          interval={0}
          tick={<RotuloDoMes pontos={pontos} />}
          height={24}
        />
        <YAxis hide domain={[0, "auto"]} />
        <Tooltip
          content={<Dica />}
          cursor={{ stroke: "#30302d", strokeWidth: 1 }}
          isAnimationActive={false}
        />
        <Line
          type="monotone"
          dataKey="valor"
          stroke={COR_SERIE}
          strokeWidth={2}
          isAnimationActive={false}
          connectNulls={false}
          // Ponto só no mês selecionado: é o que situa a linha. Um ponto por
          // mês viraria um colar que disputa com a própria linha.
          dot={(props) => {
            // O Recharts manda a `key` dentro das props; espalhá-la no JSX é
            // o que o React recusa.
            const { key, ...resto } = props as typeof props & { key?: string };
            return <PontoAtual key={key ?? props.index} {...resto} />;
          }}
          activeDot={{ r: 5, fill: COR_SERIE, stroke: "#121211", strokeWidth: 2 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

function PontoAtual(props: { cx?: number; cy?: number; payload?: PontoEvolucao }) {
  const { cx, cy, payload } = props;
  if (!payload?.atual || cx == null || cy == null) return <g />;
  return <circle cx={cx} cy={cy} r={5} fill={COR_SERIE} stroke="#121211" strokeWidth={2} />;
}

function RotuloDoMes(props: {
  x?: number;
  y?: number;
  payload?: { value: string; index: number };
  pontos: PontoEvolucao[];
}) {
  const { x = 0, y = 0, payload, pontos } = props;
  const ponto = payload ? pontos[payload.index] : undefined;
  // Com doze meses em 360px, um rótulo por mês não cabe: mostra um sim, um
  // não — sempre incluindo o mês atual, que é o que situa a leitura.
  const n = pontos.length;
  const idx = payload?.index ?? 0;
  const mostra = n <= 7 || ponto?.atual || (n - 1 - idx) % 2 === 0;
  if (!mostra) return <g />;
  return (
    <text
      x={x}
      y={y + 12}
      textAnchor="middle"
      className={`recharts-cartesian-axis-tick-value${ponto?.atual ? " atual" : ""}`}
    >
      {payload?.value}
    </text>
  );
}

function Dica({ active, payload }: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null;
  const ponto = payload[0].payload as PontoEvolucao;
  return (
    <div className="tooltip">
      <div className="t">{ponto.mesLongo}</div>
      {ponto.valor == null ? (
        <span className="t">sem finalidade registrada</span>
      ) : (
        <b className="tnum">{formatMoney(ponto.valor)}</b>
      )}
    </div>
  );
}
