"""Cobre o esquema de assinatura que o Supabase usa hoje.

Projeto novo assina com ES256 e publica a chave pública no JWKS; o "JWT Secret"
HS256 é o caminho legado. Validar só HS256 rejeitava todo token real — foi o bug
que derrubou o primeiro login, e estes testes existem pra ele não voltar.
"""
import datetime as dt

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from app import auth

USER_ID = "11111111-1111-1111-1111-111111111111"
KID = "chave-de-teste"
JWKS_URL = "https://projeto-de-teste.supabase.co/auth/v1/.well-known/jwks.json"


def _par_de_chaves():
    privada = ec.generate_private_key(ec.SECP256R1())
    return privada, privada.public_key()


@pytest.fixture(name="es256")
def es256_fixture(monkeypatch):
    """Configura o app pra ES256 e serve a pública sem ir à rede."""
    privada, publica = _par_de_chaves()

    monkeypatch.setenv("SUPABASE_URL", "https://projeto-de-teste.supabase.co")
    monkeypatch.setenv("SENTAVOS_ALLOWED_USER_ID", USER_ID)
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)

    class ChaveFake:
        key = publica

    class ClienteFake:
        def __init__(self, url, **kwargs):
            self.url = url

        def get_signing_key_from_jwt(self, token):
            return ChaveFake()

    # O lru_cache guardaria o cliente real entre testes.
    auth._cliente_jwks.cache_clear()
    monkeypatch.setattr(auth.jwt, "PyJWKClient", ClienteFake)

    yield privada
    auth._cliente_jwks.cache_clear()


def token_es256(privada, sub=USER_ID, minutos=10, aud="authenticated"):
    agora = dt.datetime.now(dt.timezone.utc)
    return jwt.encode(
        {"sub": sub, "aud": aud, "exp": agora + dt.timedelta(minutes=minutos)},
        privada,
        algorithm="ES256",
        headers={"kid": KID},
    )


def test_token_es256_valido_entra(anon_client, es256):
    r = anon_client.get(
        "/transactions", headers={"Authorization": f"Bearer {token_es256(es256)}"}
    )

    assert r.status_code == 200


def test_es256_de_outra_chave_da_401(anon_client, es256):
    # Assinado por um par diferente do que o JWKS publica.
    outra, _ = _par_de_chaves()

    r = anon_client.get(
        "/transactions", headers={"Authorization": f"Bearer {token_es256(outra)}"}
    )

    assert r.status_code == 401


def test_es256_expirado_da_401(anon_client, es256):
    r = anon_client.get(
        "/transactions",
        headers={"Authorization": f"Bearer {token_es256(es256, minutos=-5)}"},
    )

    assert r.status_code == 401


def test_es256_de_outro_usuario_da_403(anon_client, es256):
    intruso = token_es256(es256, sub="22222222-2222-2222-2222-222222222222")

    r = anon_client.get("/transactions", headers={"Authorization": f"Bearer {intruso}"})

    assert r.status_code == 403


def test_alg_none_e_recusado(anon_client, es256):
    # Sem a lista fechada de algoritmos, um token sem assinatura passaria.
    sem_assinatura = jwt.encode({"sub": USER_ID, "aud": "authenticated"}, key=None, algorithm="none")

    r = anon_client.get(
        "/transactions", headers={"Authorization": f"Bearer {sem_assinatura}"}
    )

    assert r.status_code == 401


def test_hs256_nao_passa_com_a_publica_como_segredo(anon_client, es256):
    """Confusão de algoritmo: forjar HS256 usando a chave pública como segredo.

    É o ataque clássico contra quem aceita mais de um algoritmo, e a chave
    pública serve pra ele porque é pública. Montado à mão de propósito: o
    jwt.encode se recusa a usar PEM como segredo HMAC, então usar ele aqui
    testaria a proteção da biblioteca em vez da nossa.

    Não cola porque HS256 é verificado contra o segredo do painel, não contra a
    pública — e neste cenário o segredo nem está configurado.
    """
    import base64
    import hashlib
    import hmac
    import json

    from cryptography.hazmat.primitives import serialization

    publica_pem = es256.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    def b64(dados: bytes) -> bytes:
        return base64.urlsafe_b64encode(dados).rstrip(b"=")

    agora = dt.datetime.now(dt.timezone.utc)
    cabecalho = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    corpo = b64(
        json.dumps(
            {
                "sub": USER_ID,
                "aud": "authenticated",
                "exp": int((agora + dt.timedelta(minutes=10)).timestamp()),
            }
        ).encode()
    )
    assinatura = b64(
        hmac.new(publica_pem, cabecalho + b"." + corpo, hashlib.sha256).digest()
    )
    forjado = b".".join([cabecalho, corpo, assinatura]).decode()

    r = anon_client.get("/transactions", headers={"Authorization": f"Bearer {forjado}"})

    assert r.status_code == 401


def test_jwks_fora_do_ar_da_503_e_nao_200(anon_client, monkeypatch):
    # Falha de infraestrutura não pode virar "entre de novo" nem liberar acesso.
    monkeypatch.setenv("SUPABASE_URL", "https://projeto-de-teste.supabase.co")
    monkeypatch.setenv("SENTAVOS_ALLOWED_USER_ID", USER_ID)
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)

    privada, _ = _par_de_chaves()

    class ClienteQuebrado:
        def __init__(self, url, **kwargs):
            pass

        def get_signing_key_from_jwt(self, token):
            raise ConnectionError("jwks indisponível")

    auth._cliente_jwks.cache_clear()
    monkeypatch.setattr(auth.jwt, "PyJWKClient", ClienteQuebrado)

    r = anon_client.get(
        "/transactions", headers={"Authorization": f"Bearer {token_es256(privada)}"}
    )
    auth._cliente_jwks.cache_clear()

    assert r.status_code == 503
