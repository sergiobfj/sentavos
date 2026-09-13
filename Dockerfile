# Imagem da API do Sentavos. O Railway detecta este arquivo sozinho e ignora o
# buildpack automático — que aqui erraria, porque o projeto usa uv e não um
# requirements.txt.
FROM python:3.12-slim

# O uv vem da imagem oficial dele em vez de `pip install uv`: é uma cópia de
# binário, não uma resolução de dependência a mais dentro do build.
COPY --from=ghcr.io/astral-sh/uv:0.11.24 /uv /bin/uv

WORKDIR /srv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/srv/.venv \
    PYTHONUNBUFFERED=1

# As dependências entram antes do código de propósito: elas mudam pouco, então
# esta camada fica em cache e o deploy de uma alteração em app/ não reinstala
# tudo de novo.
#
# --frozen exige que o uv.lock esteja de acordo com o pyproject.toml. Se você
# mexer nas dependências e esquecer de rodar `uv lock`, o build falha aqui em
# vez de subir uma versão diferente da que você testou na sua máquina.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app

ENV PATH="/srv/.venv/bin:$PATH"

# Roda como usuário comum. Se algum dia uma falha der execução de código dentro
# do container, root faz muito mais estrago do que um usuário que nem consegue
# escrever no próprio código da aplicação — que é por isso que o chown deixa os
# arquivos com o dono anterior e só a pasta de trabalho acessível pra leitura.
RUN useradd --create-home --uid 10001 sentavos && chown -R root:root /srv
USER sentavos

# Forma shell (sem colchetes) porque o $PORT precisa ser expandido pelo shell: o
# Railway sorteia a porta a cada deploy e injeta na variável. Em colchetes, o
# uvicorn receberia a string "$PORT" crua e não subiria.
#
# --host 0.0.0.0 é obrigatório no container: o padrão 127.0.0.1 só aceitaria
# conexão de dentro dele mesmo, e o roteador do Railway nunca chegaria.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --forwarded-allow-ips='*'
