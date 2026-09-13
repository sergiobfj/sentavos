"""Gera o hash da sua senha e o segredo do JWT, pra colar no host.

    uv run python -m app.criar_senha

A senha é pedida escondida (não aparece na tela nem fica no histórico do shell) e
o que sai é só o hash — de onde não dá pra voltar pra senha. É o hash que vai pro
Railway, nunca a senha em si.
"""

import getpass
import secrets
import sys

from app.auth import gerar_hash


def main() -> int:
    print("Sentavos — configuração de acesso\n")

    email = input("Seu e-mail: ").strip().lower()
    if not email or "@" not in email:
        print("\nE-mail inválido.", file=sys.stderr)
        return 1

    senha = getpass.getpass("Senha (não aparece enquanto digita): ")
    if len(senha) < 12:
        # Não é burocracia: este é o único segredo entre a internet e as suas
        # finanças, e o rate limit da API atrasa quem tenta adivinhar, não impede.
        print("\nUse pelo menos 12 caracteres.", file=sys.stderr)
        return 1

    if senha != getpass.getpass("Repita a senha: "):
        print("\nAs senhas não conferem.", file=sys.stderr)
        return 1

    print("\n" + "=" * 72)
    print("Cole estas três variáveis no Railway (Variables):")
    print("=" * 72 + "\n")
    print(f"SENTAVOS_EMAIL={email}")
    print(f"SENTAVOS_SENHA_HASH={gerar_hash(senha)}")
    # token_hex(32) = 256 bits de entropia. É o segredo que assina os tokens:
    # quem tiver ele emite acesso sem precisar da senha.
    print(f"SENTAVOS_JWT_SECRET={secrets.token_hex(32)}")
    print("\n" + "=" * 72)
    print("O hash pode ser público sem risco — a senha não sai dele.")
    print("O SENTAVOS_JWT_SECRET é segredo de verdade: trate como senha.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
