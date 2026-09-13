"""Lê a planilha "Controle Financeiro" e importa pro banco do Sentavos.

    # Só relatório, não escreve nada (padrão):
    uv run --with openpyxl python -m scripts.importar_planilha "planilha.xlsx"

    # Escreve de verdade:
    uv run --with openpyxl python -m scripts.importar_planilha "planilha.xlsx" --aplicar

    # Reimportar do zero (apaga o que a importação anterior criou no período):
    uv run --with openpyxl python -m scripts.importar_planilha "planilha.xlsx" --aplicar --limpar

O padrão é **modo seco**: lê tudo, monta o que seria criado e imprime o resumo,
sem encostar no banco. Escrever exige `--aplicar` de propósito — uma importação
errada num banco já em uso é muito mais cara de desfazer do que de evitar.

## A forma da planilha

Os dois anos são tabelas de quadrimestre com meses lado a lado, não uma lista.
Cada mês ocupa um grupo de colunas, e as seções se empilham na vertical,
repetidas em cada mês do grupo:

        col A..E        col G..K        col M..Q        col S..W
      ┌──────────────┬──────────────┬──────────────┬──────────────┐
      │ JANEIRO      │ FEVEREIRO    │ MARÇO        │ ABRIL        │
      │  ENTRADAS    │  ENTRADAS    │  ENTRADAS    │  ENTRADAS    │
      │  DESP FIXAS  │  DESP FIXAS  │  ...         │  ...         │
      │  DESP VAR    │  ...         │              │              │
      │  INVESTIMENTO│              │              │              │
      │  SALDO CONTA │              │              │              │
      └──────────────┴──────────────┴──────────────┴──────────────┘

2025 e 2026 têm formatos diferentes, e a diferença importa:

  2026 — 4 meses por bloco, 6 colunas cada: DIA, DESCRIÇÃO, VALOR PAGO,
         VALOR A PAGAR, OBS, (vazia). Tem previsto E pago.
  2025 — 6 meses por bloco, 4 colunas cada: DIA, DESCRIÇÃO, VALOR, (vazia).
         Só tem o valor realizado; não existe "a pagar".

Por isso todo lançamento de 2025 entra com `amount_planned` vazio. Não é perda
de dado: o dado nunca existiu.
"""

import argparse
import datetime as dt
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import openpyxl
from sqlmodel import Session, select

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine  # noqa: E402
from app.models import (  # noqa: E402
    Asset,
    AssetClass,
    AssetSnapshot,
    Category,
    CategoryType,
    Transaction,
)

MESES = {
    "JANEIRO": 1, "FEVEREIRO": 2, "MARCO": 3, "ABRIL": 4,
    "MAIO": 5, "JUNHO": 6, "JULHO": 7, "AGOSTO": 8,
    "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12,
}

# O nome da seção é o que decide o tipo do lançamento. A planilha separa despesa
# fixa de variável, distinção que o Sentavos guarda na categoria, não no tipo.
SECOES = {
    "ENTRADAS": ("entradas", CategoryType.INCOME),
    "RECEBIDOS": ("entradas", CategoryType.INCOME),
    "DESPESAS FIXAS": ("fixas", CategoryType.EXPENSE),
    "DESPESAS VAR": ("variáveis", CategoryType.EXPENSE),
    "INVESTIMENTO": ("investimento", CategoryType.INVESTMENT),
}

SALDO_CONTA = "SALDO EM CONTA"
SALDO_INVEST = "SALDO EM INVESTIMENTO"

# Os dois ativos que os saldos mensais viram na aba Patrimônio.
ATIVOS = {
    "conta": ("Conta", AssetClass.CHECKING, "Saldo em conta, vindo da planilha."),
    "investimento": ("Investimento", AssetClass.FIXED_INCOME,
                     "Saldo aplicado, vindo da planilha."),
}

# Emoji por categoria conhecida. O que não estiver aqui cai no padrão do tipo.
ICONES = {
    "INTERNET": "🌐", "ACADEMIA": "🏋️", "SALARIO": "💰", "SALARIO 15": "💰",
    "META": "🎯", "CABELO": "✂️", "FATURA": "💳", "UBER": "🚗", "LANCHE": "🍔",
    "DIETA": "🥗", "CNH": "🪪", "ASSINATURA": "📺", "ASSINATURAS": "📺",
    "SECCO": "🏢", "BIA": "💝", "MAE": "👩", "TRANSPORTE": "🚌", "AJUSTE": "⚖️",
    "RESERVA": "🏦", "CAIXINHA EM": "🏦", "CAIXINHA 5K": "🏦",
    "CAIXINHA 5K M PAGO": "🏦", "INVESTMENTO 5K M PAGO": "🏦",
    "CASA": "🏠", "FACUL": "🎓", "SUPLEMENTO": "💊", "SUPLEMENTOS": "💊",
}
ICONE_PADRAO = {
    CategoryType.INCOME: "💵",
    CategoryType.EXPENSE: "💸",
    CategoryType.INVESTMENT: "📈",
}

# Paletas por tipo, alinhadas com as variáveis de cor do index.css. Cicladas pra
# categorias do mesmo tipo não ficarem todas da mesma cor na tela.
PALETAS = {
    CategoryType.INCOME: ["#35b36b", "#2e9e5e", "#48c47d", "#1f8a4d"],
    CategoryType.EXPENSE: ["#ef5350", "#e07a5f", "#d64550", "#c9705a", "#f07470"],
    CategoryType.INVESTMENT: ["#6b8afd", "#5a78e8", "#8aa2ff", "#4c68d4"],
}


def sem_acento(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )


# Nomes que são a mesma coisa escrita de jeitos diferentes ao longo do tempo.
#
# A caixinha de 5 mil foi rebatizada duas vezes na planilha ("CAIXINHA 5K" →
# "CAIXINHA 5K M PAGO" → "INVESTMENTO 5K M PAGO"), e sem unificar a aba de
# Investimento mostraria três categorias que são o mesmo dinheiro — com o
# gráfico de composição dividindo uma aplicação só em três fatias.
#
# A tabela é explícita, e não uma heurística de semelhança, porque adivinhar
# aqui erraria: "CAIXINHA EM" (emergência) parece "CAIXINHA 5K" e é outra coisa.
ALIASES = {
    "ASSINATURAS": "ASSINATURA",
    "SUPLEMENTOS": "SUPLEMENTO",
    "CAIXINHA 5K NUBANK": "CAIXINHA 5K",
    "CAIXINHA 5K M PAGO": "CAIXINHA 5K",
    "INVESTMENTO 5K M PAGO": "CAIXINHA 5K",
}


def normalizar(valor) -> str:
    """Caixa alta, sem acento e sem espaço duplicado — pra agrupar 'Cabelo',
    'CABELO' e 'cabelo ' como a mesma coisa. Depois aplica os ALIASES."""
    texto = re.sub(r"\s+", " ", sem_acento(str(valor)).upper()).strip()
    return ALIASES.get(texto, texto)


def como_numero(valor) -> float | None:
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip().replace("R$", "").replace(" ", "")
    if not texto:
        return None
    if "," in texto:  # formato brasileiro: 1.234,56
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return None


@dataclass
class Lancamento:
    ano: int
    mes: int
    dia: int | None
    descricao: str
    pago: float | None
    previsto: float | None
    obs: str | None
    secao: str
    tipo: CategoryType
    origem: str

    @property
    def data(self) -> dt.date:
        # Sem dia informado, o lançamento vai pro dia 1. A alternativa seria
        # descartá-lo, e perder o valor é pior que perder a precisão do dia.
        dia = self.dia if self.dia and 1 <= self.dia <= 28 else 1
        try:
            return dt.date(self.ano, self.mes, dia)
        except ValueError:
            return dt.date(self.ano, self.mes, 1)


@dataclass
class Saldo:
    ano: int
    mes: int
    valor: float
    qual: str


@dataclass
class Leitura:
    lancamentos: list[Lancamento] = field(default_factory=list)
    saldos: list[Saldo] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def _rotulo_mes(ws, linha: int, col: int) -> str | None:
    bruto = ws.cell(row=linha, column=col).value
    if not bruto:
        return None
    texto = normalizar(bruto)
    for nome in MESES:
        if nome in texto:
            return nome
    return None


def _secao_da_linha(ws, linha: int, col: int) -> tuple[str, CategoryType] | None:
    bruto = ws.cell(row=linha, column=col).value
    if not bruto:
        return None
    texto = normalizar(bruto)
    for chave, valor in SECOES.items():
        if chave in texto:
            return valor
    return None


def _ler_mes(ws, ano, mes, col, tem_previsto, inicio, fim) -> Leitura:
    leitura = Leitura()
    secao_atual = None
    linha = inicio

    while linha < fim:
        # O cabeçalho da seção pode estar na coluna do mês (onde o nome do mês e
        # a seção vêm juntos) ou na coluna A (seções seguintes).
        nova = _secao_da_linha(ws, linha, col) or _secao_da_linha(ws, linha, 1)
        rotulo_a = normalizar(ws.cell(row=linha, column=1).value or "")

        if SALDO_CONTA in rotulo_a or SALDO_INVEST in rotulo_a:
            qual = "conta" if SALDO_CONTA in rotulo_a else "investimento"
            valor = como_numero(ws.cell(row=linha + 1, column=col).value)
            if valor is not None:
                leitura.saldos.append(Saldo(ano=ano, mes=mes, valor=valor, qual=qual))
            secao_atual = None
            linha += 2
            continue

        if nova:
            secao_atual = nova
            linha += 2  # pula o cabeçalho DIA/DESCRIÇÃO/VALOR
            continue

        if secao_atual is None or rotulo_a.startswith("TOTAL"):
            if rotulo_a.startswith("TOTAL"):
                secao_atual = None
            linha += 1
            continue

        dia = como_numero(ws.cell(row=linha, column=col).value)
        descricao = ws.cell(row=linha, column=col + 1).value
        pago = como_numero(ws.cell(row=linha, column=col + 2).value)
        if tem_previsto:
            previsto = como_numero(ws.cell(row=linha, column=col + 3).value)
            obs = ws.cell(row=linha, column=col + 4).value
        else:
            previsto, obs = None, None

        texto = str(descricao).strip() if descricao is not None else ""
        celula = f"{ws.title}!{openpyxl.utils.get_column_letter(col + 1)}{linha}"

        if texto and (pago is not None or previsto is not None):
            secao, tipo = secao_atual
            leitura.lancamentos.append(
                Lancamento(
                    ano=ano, mes=mes, dia=int(dia) if dia else None, descricao=texto,
                    pago=pago, previsto=previsto,
                    obs=str(obs).strip() if obs else None,
                    secao=secao, tipo=tipo, origem=celula,
                )
            )
        elif texto:
            leitura.avisos.append(f"{celula}: '{texto}' sem valor — ignorado.")
        elif pago is not None or previsto is not None:
            leitura.avisos.append(
                f"{celula}: valor {pago if pago is not None else previsto} "
                f"sem descrição — ignorado."
            )

        linha += 1

    return leitura


def ler_aba(ws, ano: int, inicios: list[int], tem_previsto: bool, duplicado: str) -> Leitura:
    """Lê uma aba inteira.

    `inicios` são as colunas onde cada mês do bloco começa. Muda entre 2025 e
    2026 — ver o docstring do módulo.
    """
    total = Leitura()
    # Um mês pode aparecer duas vezes na mesma aba (2025 tem DEZEMBRO duplicado,
    # com números diferentes). Importar os dois somaria o mês em dobro, então
    # cada ocorrência é lida separada e só uma sobrevive.
    ocorrencias: dict[int, list[tuple[int, Leitura]]] = defaultdict(list)

    linhas_de_mes = [
        linha for linha in range(1, ws.max_row + 1) if _rotulo_mes(ws, linha, inicios[0])
    ]

    for indice, linha_meses in enumerate(linhas_de_mes):
        fim = linhas_de_mes[indice + 1] if indice + 1 < len(linhas_de_mes) else ws.max_row + 1
        for col in inicios:
            nome = _rotulo_mes(ws, linha_meses, col)
            if not nome:
                continue
            mes = MESES[nome]
            ocorrencias[mes].append(
                (col, _ler_mes(ws, ano, mes, col, tem_previsto, linha_meses, fim))
            )

    for mes, lista in sorted(ocorrencias.items()):
        escolhida = lista[-1] if duplicado == "ultimo" else lista[0]
        if len(lista) > 1:
            descartadas = [c for c, _ in lista if c != escolhida[0]]
            total.avisos.append(
                f"{ws.title}: mês {mes:02d} aparece {len(lista)}x. Ficou a coluna "
                f"{openpyxl.utils.get_column_letter(escolhida[0])}; ignoradas: "
                + ", ".join(openpyxl.utils.get_column_letter(c) for c in descartadas)
            )
        total.lancamentos += escolhida[1].lancamentos
        total.saldos += escolhida[1].saldos
        total.avisos += escolhida[1].avisos

    return total


def ler_planilha(caminho: str, duplicado: str) -> Leitura:
    wb = openpyxl.load_workbook(caminho, data_only=True)
    total = Leitura()

    if "2025" in wb.sheetnames:
        r = ler_aba(wb["2025"], 2025, [1, 5, 9, 13, 17, 21], False, duplicado)
        total.lancamentos += r.lancamentos
        total.saldos += r.saldos
        total.avisos += r.avisos

    if "2026" in wb.sheetnames:
        r = ler_aba(wb["2026"], 2026, [1, 7, 13, 19], True, duplicado)
        total.lancamentos += r.lancamentos
        total.saldos += r.saldos
        total.avisos += r.avisos

    return total


# ---------- Do que foi lido pro modelo do Sentavos ----------

@dataclass
class Plano:
    """O que seria escrito. Montado antes de tocar no banco, pra poder ser
    conferido em modo seco."""
    categorias: dict[tuple[str, CategoryType], str]  # (nome normalizado, tipo) -> rótulo
    por_lancamento: dict[int, tuple[str, CategoryType]]  # id(lançamento) -> chave
    lancamentos: list[Lancamento]
    saldos: list[Saldo]
    avisos: list[str]


def montar_plano(leitura: Leitura, recorrencia: int, corte: tuple[int, int]) -> Plano:
    # Uma descrição só vira categoria própria se se repetir. O resto vai pra
    # "Outros" da seção: 60 categorias de um lançamento só não ajudam ninguém a
    # entender pra onde o dinheiro foi.
    frequencia = Counter(normalizar(l.descricao) for l in leitura.lancamentos)
    recorrentes = {n for n, q in frequencia.items() if q >= recorrencia}

    # O rótulo exibido é a grafia mais comum na planilha, não a normalizada —
    # "Cabelo" lê melhor que "CABELO" e é o que ele já reconhece.
    grafias: dict[str, Counter] = defaultdict(Counter)
    for l in leitura.lancamentos:
        grafias[normalizar(l.descricao)][l.descricao.strip()] += 1

    # Um mesmo nome pode cair em tipos diferentes (CNH é despesa e investimento;
    # AJUSTE é entrada e despesa). Categoria tem um tipo só, então a chave é o
    # par nome+tipo e o rótulo ganha sufixo quando há conflito.
    tipos_por_nome: dict[str, set] = defaultdict(set)
    for l in leitura.lancamentos:
        nome = normalizar(l.descricao)
        if nome in recorrentes:
            tipos_por_nome[nome].add(l.tipo)

    categorias: dict[tuple[str, CategoryType], str] = {}
    por_lancamento: dict[int, tuple[str, CategoryType]] = {}

    for l in leitura.lancamentos:
        nome = normalizar(l.descricao)
        if nome in recorrentes:
            chave = (nome, l.tipo)
            if chave not in categorias:
                rotulo = grafias[nome].most_common(1)[0][0]
                if len(tipos_por_nome[nome]) > 1:
                    rotulo = f"{rotulo} ({l.secao})"
                categorias[chave] = rotulo
        else:
            chave = (f"OUTROS {l.secao.upper()}", l.tipo)
            categorias.setdefault(chave, f"Outros ({l.secao})")
        por_lancamento[id(l)] = chave

    limite = corte[0] * 12 + corte[1]
    saldos = [s for s in leitura.saldos if s.ano * 12 + s.mes <= limite]
    cortados = len(leitura.saldos) - len(saldos)
    avisos = list(leitura.avisos)
    if cortados:
        avisos.append(
            f"{cortados} saldo(s) depois de {corte[0]}-{corte[1]:02d} ficaram de fora: "
            f"são valor arrastado de mês futuro, não saldo lançado."
        )

    return Plano(categorias, por_lancamento, leitura.lancamentos, saldos, avisos)


def icone_e_cor(nome: str, tipo: CategoryType, indice: int) -> tuple[str, str]:
    icone = ICONES.get(nome, ICONE_PADRAO[tipo])
    paleta = PALETAS[tipo]
    return icone, paleta[indice % len(paleta)]


# ---------- Relatório ----------

def relatorio(plano: Plano) -> None:
    print("=" * 74)
    print("O QUE SERIA CRIADO")
    print("=" * 74)

    por_periodo = Counter((l.ano, l.mes) for l in plano.lancamentos)
    print(f"\nLançamentos: {len(plano.lancamentos)}  em {len(por_periodo)} meses")
    print(f"Categorias:  {len(plano.categorias)}")
    print(f"Ativos:      {len(ATIVOS)}  (Conta e Investimento)")
    print(f"Saldos:      {len(plano.saldos)}")

    print("\n--- Categorias ---")
    porte = Counter(plano.por_lancamento.values())
    for tipo in CategoryType:
        do_tipo = [(k, v) for k, v in plano.categorias.items() if k[1] == tipo]
        if not do_tipo:
            continue
        print(f"\n  {tipo.value}:")
        for chave, rotulo in sorted(do_tipo, key=lambda x: -porte[x[0]]):
            print(f"      {porte[chave]:3}x  {rotulo}")

    print("\n--- Conferência: total pago por mês ---")
    soma: dict[tuple[int, int], float] = defaultdict(float)
    for l in plano.lancamentos:
        if l.pago is not None:
            soma[(l.ano, l.mes)] += l.pago
    for periodo in sorted(soma):
        print(f"      {periodo[0]}-{periodo[1]:02d}:  {soma[periodo]:>10,.2f}")

    if plano.avisos:
        print(f"\n--- Avisos: {len(plano.avisos)} ---")
        for aviso in plano.avisos:
            print(f"      - {aviso}")


# ---------- Escrita ----------

def aplicar(plano: Plano, limpar: bool) -> None:
    datas = [l.data for l in plano.lancamentos]
    inicio, fim = min(datas), max(datas)

    with Session(engine) as s:
        if limpar:
            # Só o intervalo importado, e só o que a importação cria. Lançamento
            # que você digitou fora desse período continua onde está.
            antigas = s.exec(
                select(Transaction).where(Transaction.date >= inicio, Transaction.date <= fim)
            ).all()
            for t in antigas:
                s.delete(t)
            nomes = [nome for nome, _, _ in ATIVOS.values()]
            for ativo in s.exec(select(Asset).where(Asset.name.in_(nomes))).all():
                for snap in s.exec(
                    select(AssetSnapshot).where(AssetSnapshot.asset_id == ativo.id)
                ).all():
                    s.delete(snap)
            s.flush()
            print(f"   limpeza: {len(antigas)} lançamento(s) e os saldos dos ativos da planilha")

        existentes = {
            (normalizar(c.name), c.type): c for c in s.exec(select(Category)).all()
        }

        ids: dict[tuple[str, CategoryType], int] = {}
        criadas = reaproveitadas = 0
        for indice, (chave, rotulo) in enumerate(sorted(plano.categorias.items())):
            # Casa pelo rótulo normalizado: se você já criou "Academia" na mão,
            # a importação usa a sua em vez de criar uma segunda igual.
            achada = existentes.get((normalizar(rotulo), chave[1]))
            if achada:
                ids[chave] = achada.id
                reaproveitadas += 1
                continue
            icone, cor = icone_e_cor(chave[0], chave[1], indice)
            nova = Category(name=rotulo, type=chave[1], color=cor, icon=icone)
            s.add(nova)
            s.flush()
            ids[chave] = nova.id
            criadas += 1
        print(f"   categorias: {criadas} criada(s), {reaproveitadas} reaproveitada(s)")

        for l in plano.lancamentos:
            s.add(Transaction(
                date=l.data,
                description=l.descricao.strip(),
                amount_planned=l.previsto,
                amount_paid=l.pago,
                note=l.obs,
                category_id=ids[plano.por_lancamento[id(l)]],
            ))
        print(f"   lançamentos: {len(plano.lancamentos)}")

        ativos: dict[str, int] = {}
        for qual, (nome, classe, nota) in ATIVOS.items():
            achado = s.exec(select(Asset).where(Asset.name == nome)).first()
            if not achado:
                achado = Asset(name=nome, asset_class=classe, note=nota)
                s.add(achado)
                s.flush()
            ativos[qual] = achado.id

        for saldo in plano.saldos:
            s.add(AssetSnapshot(
                asset_id=ativos[saldo.qual], year=saldo.ano,
                month=saldo.mes, value=saldo.valor,
            ))
        print(f"   saldos: {len(plano.saldos)}")

        s.commit()
    print("\n   gravado.")


def main() -> int:
    p = argparse.ArgumentParser(description="Importa a planilha pro Sentavos.")
    p.add_argument("planilha")
    p.add_argument("--aplicar", action="store_true", help="escreve no banco")
    p.add_argument("--limpar", action="store_true",
                   help="apaga o período antes de escrever (pra reimportar sem duplicar)")
    p.add_argument("--recorrencia", type=int, default=3,
                   help="quantas vezes uma descrição precisa aparecer pra virar categoria")
    p.add_argument("--ate", default="2026-09",
                   help="último mês com saldo real (AAAA-MM); depois disso é valor arrastado")
    p.add_argument("--duplicado", choices=["ultimo", "primeiro"], default="ultimo",
                   help="qual coluna vence quando o mesmo mês aparece duas vezes")
    args = p.parse_args()

    ano, mes = (int(x) for x in args.ate.split("-"))
    leitura = ler_planilha(args.planilha, args.duplicado)
    plano = montar_plano(leitura, args.recorrencia, (ano, mes))
    relatorio(plano)

    if not args.aplicar:
        print("\n" + "=" * 74)
        print("MODO SECO — nada foi escrito. Use --aplicar pra gravar.")
        print("=" * 74)
        return 0

    print("\n" + "=" * 74)
    print("GRAVANDO")
    print("=" * 74)
    aplicar(plano, args.limpar)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
