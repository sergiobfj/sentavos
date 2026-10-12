"""Um relógio só: o dia e o instante de referência, no fuso do Brasil.

`hoje()` é o dia local (UTC−3) — no servidor (UTC), `date.today()` virava o
dia seguinte depois das 21h. `agora()` é o instante, coerente com `hoje()`:
quando um teste fixa o dia (monkeypatch em `app.planejamento.hoje`), o
instante cai nesse dia, na hora corrente.
"""

import datetime as dt

# Brasil sem horário de verão desde 2019: UTC−3 fixo, sem depender do banco de
# fusos do sistema (o Windows não traz o IANA).
FUSO = dt.timezone(dt.timedelta(hours=-3), "BRT")


def hoje_local() -> dt.date:
    return dt.datetime.now(FUSO).date()


def agora() -> dt.datetime:
    """Instante de referência, em UTC, no dia que `planejamento.hoje()` diz."""
    from app import planejamento  # tardio: planejamento importa daqui

    real = dt.datetime.now(FUSO)
    dia = planejamento.hoje()
    if dia == real.date():
        return real.astimezone(dt.timezone.utc)
    return dt.datetime.combine(dia, real.timetz()).astimezone(dt.timezone.utc)
