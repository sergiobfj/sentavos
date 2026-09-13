"""Cria ou atualiza uma conta do Sentavos.

    uv run python -m app.criar_usuario

Pergunta os dados, pede a senha escondida e escreve direto no banco apontado
por DATABASE_URL. Não existe cadastro pela interface de propósito: num app de
três pessoas, um formulário aberto seria superfície pra proteger sem ninguém
pra usar.

Rodar de novo com um e-mail que já existe troca a senha — que é como se
recupera acesso, já que não há "esqueci minha senha".
"""

import getpass
import secrets
import sys

from sqlmodel import Session, select

from app.auth import gerar_hash
from app.database import engine
from app.models import User


def main() -> int:
    print("Sentavos — criar ou atualizar conta\n")

    email = input("E-mail: ").strip().lower()
    if not email or "@" not in email:
        print("\nE-mail inválido.", file=sys.stderr)
        return 1

    with Session(engine) as s:
        existente = s.exec(select(User).where(User.email == email)).first()

        if existente:
            print(f"\nJá existe conta para {email} ({existente.name}).")
            if input("Trocar a senha dela? [s/N]: ").strip().lower() != "s":
                print("Nada foi alterado.")
                return 0
            nome = existente.name
        else:
            nome = input("Nome: ").strip() or email.split("@")[0]

        senha = getpass.getpass("Senha (não aparece enquanto digita): ")
        if len(senha) < 12:
            # Não é burocracia: esta senha é o que separa a internet das
            # finanças de alguém, e o rate limit atrasa quem tenta adivinhar,
            # não impede.
            print("\nUse pelo menos 12 caracteres.", file=sys.stderr)
            return 1
        if senha != getpass.getpass("Repita a senha: "):
            print("\nAs senhas não conferem.", file=sys.stderr)
            return 1

        somente_leitura = False
        if not existente:
            resposta = input("É conta de demonstração (só leitura)? [s/N]: ")
            somente_leitura = resposta.strip().lower() == "s"

        if existente:
            existente.password_hash = gerar_hash(senha)
            s.add(existente)
            acao = "senha atualizada"
        else:
            s.add(User(
                email=email, name=nome,
                password_hash=gerar_hash(senha), read_only=somente_leitura,
            ))
            acao = "conta criada"
        s.commit()

    print(f"\n{acao.capitalize()}: {email}")
    if not existente and somente_leitura:
        print("Somente leitura: esta conta navega no app mas não altera nada.")

    if not existente:
        print("\nSe este for o primeiro deploy, o servidor também precisa de:")
        print(f"SENTAVOS_JWT_SECRET={secrets.token_hex(32)}")
        print("\n(só gere um novo se ainda não houver um — trocá-lo desconecta todo mundo)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
