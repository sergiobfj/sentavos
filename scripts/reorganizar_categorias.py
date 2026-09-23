"""Reagrupa as categorias herdadas da planilha em categorias com nome de coisa.

    # Só relatório, não escreve nada (padrão):
    uv run python -m scripts.reorganizar_categorias --usuario sjunior1557@gmail.com

    # Escreve de verdade (faz backup antes):
    uv run python -m scripts.reorganizar_categorias --usuario sjunior1557@gmail.com --aplicar

## O problema

A planilha organizava gasto por SEÇÃO, não por assunto: "DESPESAS FIXAS",
"DESPESAS VARIÁVEIS", e dentro delas o que não tinha linha própria caía em
"Outros". Fazia sentido lá, onde a seção era uma região da tela que se olhava
inteira. Importado pro app, virou um conjunto de 25 categorias onde as duas
maiores eram "Outros (variáveis)" com 52 lançamentos e "FATURA" — e onde
"Chuteira", "Monitor", "Whey" e "Dia das Mães" moravam juntos, no mesmo
"Outros", por nenhum motivo além de não terem tido linha na planilha.

Categoria assim não responde "para onde foi meu dinheiro". Ela só diz que o
dinheiro saiu.

## O que este script faz

Três operações, nesta ordem, e nenhuma delas apaga lançamento:

  1. RENOMEIA a categoria que já era a dona do assunto. ACADEMIA vira Saúde,
     CABELO vira Cuidado pessoal, Item vira Eletrônicos. Renomear e não criar
     do zero preserva o id — então metas, e qualquer coisa que aponte pra ela,
     continuam de pé.

  2. RE-ARQUIVA por descrição o que estava nos dois "Outros". "MONITOR" vai pra
     Eletrônicos, "CALÇAS" pra Roupas, "PRESENTE DAVI" pra Família. A tabela é
     explícita, lançamento por descrição — não é palpite por palavra-chave, que
     acertaria "ROUPA" e erraria "FARDA".

  3. FUNDE as categorias que eram a mesma coisa com dois nomes: DIETA entra em
     Saúde, UBER em Transporte, CAIXINHA EM em Reserva de emergência. Os
     lançamentos trocam de dono e a categoria vazia é apagada.

O que não casa com nada fica em "Outros" — de propósito. Três lançamentos
("VARIEDADES", "WA", "Kit") não dá pra classificar sem perguntar, e chutar um
destino seria pior que deixar visível que eles estão sem classificação.

## Por que modo seco por padrão

Isto reescreve a categoria de centenas de lançamentos num banco em uso. O
relatório mostra cada movimento antes de qualquer escrita, e `--aplicar` grava
um backup JSON em backups/ antes de encostar no banco.
"""

import argparse
import datetime as dt
import json
import os
import sys
import unicodedata
from collections import Counter, defaultdict

from sqlmodel import Session, select

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine  # noqa: E402
from scripts.backup import salvar  # noqa: E402
from app.models import Budget, Category, CategoryType, Transaction, User  # noqa: E402


EXP = CategoryType.EXPENSE
INC = CategoryType.INCOME
INV = CategoryType.INVESTMENT


# As categorias que devem existir no fim. `doador` é a categoria atual que vira
# esta — renomeada, não recriada, pra não perder o id. Sem doador, é criada.
#
# A paleta segue index.css: vermelhos pra saída, verdes pra entrada, azuis pra
# investimento. Categorias do mesmo tipo com a mesma cor viram uma mancha só na
# tela, então as cores são cicladas dentro do tipo.
# `arquivada` é o último campo: categoria arquivada não aparece no formulário
# de lançamento, mas continua existindo e somando nos relatórios. Só "Outros"
# nasce assim — as outras 22 são pra usar.
DESTINOS = [
    # nome,                    tipo, ícone, cor,       doador,                 arquivada
    ("Mercado",                 EXP, "🛒", "#ef5350", None,                    False),
    ("Alimentação",             EXP, "🍔", "#e07a5f", "LANCHE",                False),
    ("Casa",                    EXP, "🏠", "#d64550", "INTERNET",              False),
    ("Transporte",              EXP, "🚌", "#c9705a", "Transporte",            False),
    ("Saúde",                   EXP, "🏋️", "#f07470", "ACADEMIA",              False),
    ("Cuidado pessoal",         EXP, "✂️", "#ef5350", "CABELO",                False),
    ("Roupas",                  EXP, "👕", "#e07a5f", None,                    False),
    ("Acessórios",              EXP, "👜", "#d64550", None,                    False),
    ("Eletrônicos",             EXP, "🖥️", "#c9705a", "Item",                  False),
    ("Assinaturas",             EXP, "📺", "#f07470", "ASSINATURA",            False),
    ("Lazer",                   EXP, "⚽", "#ef5350", "LAZER",                 False),
    ("Família e presentes",     EXP, "💝", "#e07a5f", "MÃE",                   False),
    ("Educação",                EXP, "🎓", "#d64550", "CNH (variáveis)",       False),
    # Duas que ficam como estão porque só você sabe o que são. A Fatura é o
    # caso mais delicado do conjunto: ver a nota no fim do relatório.
    ("Fatura do cartão",        EXP, "💳", "#c9705a", "FATURA",                False),
    ("Secco",                   EXP, "🏢", "#f07470", "SECCO",                 False),
    # O cemitério: arquivado, guardando o que não deu pra classificar.
    ("Outros",                  EXP, "🧾", "#6f6553", "Outros (variáveis)",    True),

    ("Salário",                 INC, "💰", "#35b36b", "SALÁRIO",               False),
    ("Adiantamento",            INC, "💰", "#2e9e5e", "ADIANTAMENTO",          False),
    ("Meta",                    INC, "🎯", "#48c47d", "META",                  False),
    ("Outras entradas",         INC, "💵", "#1f8a4d", "Outros (entradas)",     False),

    ("Reserva de emergência",   INV, "🏦", "#6b8afd", "CAIXINHA EM",           False),
    ("Caixinha 5K",             INV, "🏦", "#5a78e8", "CAIXINHA 5K",           False),
    ("Outros investimentos",    INV, "📈", "#8aa2ff", "Outros (investimento)", False),
]

# Categorias que se dissolvem: os lançamentos vão pro destino e elas são
# apagadas. Só entre categorias do mesmo tipo — mover despesa pra receita
# inverteria o sinal do lançamento.
FUNDIR = {
    "DIETA": "Saúde",
    "UBER": "Transporte",
    "BIA": "Família e presentes",
    "Outros (fixas)": "Outros",
    "AJUSTE (fixas)": "Outros",
    "FEIRAO (variáveis)": "Outros",
    "AJUSTE (entradas)": "Outras entradas",
    "FEIRAO (entradas)": "Outras entradas",
    "RESERVA": "Reserva de emergência",
    "CNH (investimento)": "Outros investimentos",
}

# As categorias cujos lançamentos são re-arquivados um por um, por descrição.
DILUIR = ["Outros (variáveis)", "Outros (fixas)"]

# Descrição (sem acento, maiúscula) → destino. Cada linha aqui é uma decisão
# sobre um lançamento real que existe no banco; o que não está listado fica onde
# está. "CADEIRA" vai pra Casa e não pra Eletrônicos de propósito: foi comprada
# junto com o monitor, mas cadeira é móvel.
POR_DESCRICAO = {
    # Alimentação
    "ALMOCO": "Alimentação", "PIZZA": "Alimentação", "PASTEL": "Alimentação",
    "SORVETE": "Alimentação", "DOCE": "Alimentação", "BESTEIRA": "Alimentação",
    # Lazer
    "PRAIA": "Lazer", "FUTEBOL": "Lazer", "CINEMA": "Lazer", "COPA": "Lazer",
    "ALBUM DA COPA": "Lazer", "HOTEL": "Lazer", "BAR": "Lazer",
    "REC N PLAY": "Lazer", "SAO JOAO": "Lazer", "RIFA": "Lazer",
    "SAIDA": "Lazer",
    # Roupas e acessórios
    "ROUPA": "Roupas", "CALCAS": "Roupas", "TENIS": "Roupas",
    "CASACO": "Roupas", "CAMISA": "Roupas", "CAMISA BRASIL": "Roupas",
    "FARDA": "Roupas",
    "BOLSA": "Acessórios", "OCULOS": "Acessórios",
    # Eletrônicos e casa
    "MONITOR": "Eletrônicos", "PERIFERICOS": "Eletrônicos",
    "SUPORTE": "Eletrônicos",
    "CADEIRA": "Casa", "CASA": "Casa",
    # Saúde e cuidado pessoal
    "WHEY": "Saúde", "CREATINA": "Saúde", "SUPLEMENTO": "Saúde",
    "SUPLEMENTOS": "Saúde", "DENTISTA": "Saúde",
    "COSMETICOS": "Cuidado pessoal", "HIGIENE": "Cuidado pessoal",
    # Educação
    "CADERNO": "Educação", "LIVROS": "Educação", "CURSO TECH": "Educação",
    "MATERIAIS": "Educação", "FACUL": "Educação",
    # Família e presentes
    "PRESENTE - MAE": "Família e presentes", "PRESENTE DAVI": "Família e presentes",
    "DIA DAS MAES": "Família e presentes", "EMPRESTIMO MAE": "Família e presentes",
    "CHUTEIRA - DAVI": "Família e presentes", "CASA DE VO": "Família e presentes",
    "LIVIA": "Família e presentes",
    # Resto
    "MERCADO": "Mercado",
    "CARTAO": "Fatura do cartão",
    "MOTO": "Transporte",
}


def normalizar(texto: str) -> str:
    """Sem acento, sem espaço nas pontas, maiúsculo.

    A planilha escrevia a mesma coisa de cinco jeitos ("MÃE", "MAE", "Mãe"), e
    comparar sem isso faria a tabela acima errar por causa de um til.
    """
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", texto or "")
        if unicodedata.category(c) != "Mn"
    )
    return sem_acento.strip().upper()


def backup(session: Session, dono: User) -> str:
    """Grava a conta inteira em JSON antes de escrever.

    Não é zelo genérico: este script muda o category_id de centenas de linhas,
    e não há como desfazer isso com SQL depois — a informação de onde cada
    lançamento estava só existe antes da escrita.

    A cópia em si mora em scripts/backup.py, que cobre as nove tabelas. Ficava
    aqui e salvava três; quando o cartão entrou, um backup feito por este script
    deixaria cartões, compras, faturas e pagamentos de fora sem avisar ninguém.
    """
    return salvar(session, dono, "antes-de-reagrupar-categorias")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--usuario", required=True, help="e-mail da conta")
    ap.add_argument("--aplicar", action="store_true", help="escreve no banco")
    args = ap.parse_args()

    with Session(engine) as session:
        dono = session.exec(select(User).where(User.email == args.usuario.lower())).first()
        if not dono:
            print(f"Conta não encontrada: {args.usuario}")
            return 1

        atuais = session.exec(select(Category).where(Category.user_id == dono.id)).all()
        por_nome = {normalizar(c.name): c for c in atuais}

        lancamentos = session.exec(
            select(Transaction).where(Transaction.user_id == dono.id)
        ).all()
        por_categoria: dict[int, list[Transaction]] = defaultdict(list)
        for t in lancamentos:
            por_categoria[t.category_id].append(t)

        # Resolvido ANTES de qualquer renomeação: depois de "Outros (variáveis)"
        # virar "Outros", procurar pelo nome antigo não acharia mais nada.
        diluir_ids = {
            por_nome[normalizar(n)].id: n for n in DILUIR if normalizar(n) in por_nome
        }

        print(f"\nConta: {dono.email}")
        print(f"Hoje: {len(atuais)} categorias, {len(lancamentos)} lançamentos")
        print(f"Depois: {len(DESTINOS)} categorias")

        # O backup é a PRIMEIRA escrita, antes de mexer em qualquer objeto da
        # sessão. Feito no fim, ele leria os objetos já alterados em memória e
        # salvaria o estado novo — um backup do depois, que é o mesmo que não
        # ter backup.
        if args.aplicar:
            print(f"\nBackup: {backup(session, dono)}")
        print()

        # ---------- 1. Destinos ----------
        destinos: dict[str, Category] = {}
        criadas, renomeadas, ajustadas = [], [], []

        for nome, tipo, icone, cor, doador, arquivada in DESTINOS:
            alvo = por_nome.get(normalizar(nome))

            if alvo is not None and alvo.type == tipo:
                # Já existe com este nome. Pode ser só diferença de caixa
                # ("SALÁRIO" → "Salário"), que ainda assim vale corrigir: nome
                # em caixa alta é resíduo de planilha, não ênfase.
                if alvo.name != nome:
                    ajustadas.append((alvo.name, nome))
            elif doador and normalizar(doador) in por_nome:
                alvo = por_nome[normalizar(doador)]
                renomeadas.append((alvo.name, nome, len(por_categoria[alvo.id])))
            else:
                alvo = Category(
                    name=nome, type=tipo, color=cor, icon=icone,
                    user_id=dono.id, archived=arquivada,
                )
                criadas.append(nome)
                if args.aplicar:
                    session.add(alvo)

            if args.aplicar:
                # A escrita de verdade. Sem ela o script era só um relatório
                # bonito: "ACADEMIA → Saúde" saía na tela e o banco continuava
                # com ACADEMIA.
                alvo.name = nome
                alvo.icon = icone
                alvo.color = cor
                alvo.archived = arquivada
                session.add(alvo)

            destinos[normalizar(nome)] = alvo

        if args.aplicar:
            # O flush é obrigatório aqui: as três categorias criadas do zero só
            # ganham id depois que o INSERT vai pro banco, e os passos 2 e 3
            # atribuem esse id aos lançamentos. Sem o flush, "Mercado" receberia
            # category_id = None.
            session.flush()

        print("── Renomeadas (o id e as metas continuam) ──")
        for antes, depois, n in renomeadas:
            print(f"   {antes:<22} → {depois:<22} ({n} lançamentos vêm junto)")
        if ajustadas:
            print("\n── Só a grafia (resíduo de caixa alta da planilha) ──")
            print("   " + ", ".join(f"{a} → {d}" for a, d in ajustadas))
        print("\n── Criadas do zero ──")
        print("   " + (", ".join(criadas) if criadas else "nenhuma"))

        # ---------- 2. Re-arquivar por descrição ----------
        movidos: Counter = Counter()
        sobraram: list[Transaction] = []
        plano_desc: list[tuple[str, str, str]] = []
        # Quem já saiu por descrição não pode ser contado de novo na fusão. O
        # conjunto de ids é o que faz o relatório do modo seco bater com o que
        # o --aplicar escreve: olhar `t.category_id` daria respostas diferentes
        # nos dois modos, porque só um deles altera o objeto.
        movidos_ids: set[int] = set()

        for cat_id, nome_origem in diluir_ids.items():
            for t in por_categoria[cat_id]:
                destino_nome = POR_DESCRICAO.get(normalizar(t.description))
                if destino_nome is None:
                    sobraram.append(t)
                    continue
                destino = destinos[normalizar(destino_nome)]
                plano_desc.append((nome_origem, t.description, destino_nome))
                movidos[destino_nome] += 1
                movidos_ids.add(t.id)
                if args.aplicar:
                    t.category_id = destino.id
                    session.add(t)

        print(f"\n── Re-arquivados por descrição: {sum(movidos.values())} lançamentos ──")
        for destino_nome, n in movidos.most_common():
            exemplos = [d for _, d, dest in plano_desc if dest == destino_nome][:4]
            print(f"   {destino_nome:<22} {n:>3}   ex.: {', '.join(exemplos)}")

        # ---------- 3. Fundir ----------
        print("\n── Fundidas (categoria apagada, lançamentos preservados) ──")
        for origem_nome, destino_nome in FUNDIR.items():
            origem = por_nome.get(normalizar(origem_nome))
            if origem is None:
                continue
            destino = destinos.get(normalizar(destino_nome))
            if destino is None:
                print(f"   ! {origem_nome}: destino '{destino_nome}' não existe — pulada")
                continue
            if destino.type != origem.type:
                print(f"   ! {origem_nome}: tipo diferente de '{destino_nome}' — pulada")
                continue

            restantes = [
                t for t in por_categoria[origem.id] if t.id not in movidos_ids
            ]

            print(f"   {origem.name:<22} → {destino_nome:<22} ({len(restantes)} lançamentos)")

            if args.aplicar:
                for t in restantes:
                    t.category_id = destino.id
                    session.add(t)
                metas = session.exec(
                    select(Budget).where(
                        Budget.user_id == dono.id, Budget.category_id == origem.id
                    )
                ).all()
                for m in metas:
                    session.delete(m)
                # O flush manda o UPDATE dos lançamentos e o DELETE das metas
                # antes do DELETE da categoria. Sem ele o Postgres recusa por
                # violação de chave estrangeira.
                session.flush()
                session.delete(origem)

        # ---------- 4. O que ficou sem classificação ----------
        print(f"\n── Sem classificação, ficam em 'Outros': {len(sobraram)} ──")
        for t in sobraram:
            print(f"   {t.date}  {t.description:<22} {t.amount_paid or t.amount_planned}")

        print("\n── Para você decidir depois, na tela ──")
        print("   Fatura do cartão: se você lança a fatura E as compras dela, o mês")
        print("     conta o mesmo gasto duas vezes. Vale conferir um mês.")
        print("   Secco: não sei o que é, então ficou com o nome que tinha.")
        print("   Caixinha 5K: o nome ficou, mesmo com a caixinha saindo do app —")
        print("     ali 'caixinha' é o nome do seu objetivo, não da funcionalidade.")

        if args.aplicar:
            session.commit()
            print("\nAplicado.")
        else:
            print("\nModo seco: nada foi escrito. Rode com --aplicar pra valer.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
