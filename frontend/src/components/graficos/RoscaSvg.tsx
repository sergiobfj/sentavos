import { Cell, Pie, PieChart } from "recharts";

/** O desenho da rosca, e só ele — mora num chunk separado com o Recharts.
 *
 * Tamanho fixo em vez de ResponsiveContainer: a rosca não estica com a tela
 * (uma rosca de 600px no desktop não diz mais que uma de 184), e o container
 * responsivo mediria o elemento a cada redimensionamento pra chegar no mesmo
 * número.
 */
export default function RoscaSvg({
  fatias,
  tamanho,
}: {
  fatias: { id: string; valor: number; cor: string }[];
  tamanho: number;
}) {
  return (
    <PieChart width={tamanho} height={tamanho}>
      <Pie
        data={fatias}
        dataKey="valor"
        nameKey="id"
        cx="50%"
        cy="50%"
        innerRadius={tamanho * 0.34}
        outerRadius={tamanho / 2 - 2}
        // Sentido horário a partir do topo, a maior fatia primeiro — é a
        // ordem em que o olho lê um relógio e a mesma da legenda.
        startAngle={90}
        endAngle={-270}
        // O fio de 2px da cor do fundo entre as fatias é o que separa duas
        // cores próximas; sem ele, vizinhas parecidas viram uma mancha só.
        stroke="#121211"
        strokeWidth={2}
        isAnimationActive={false}
      >
        {fatias.map((f) => (
          <Cell key={f.id} fill={f.cor} />
        ))}
      </Pie>
    </PieChart>
  );
}
