"""PvE 每日計數表的建表保險（1.36.0）。

production compose 允許把 AUTO_CREATE_SCHEMA 關掉（.env.example 就是 false）。
若只靠 Base.metadata.create_all，第一個 POST /pve/challenge 會因為找不到
pve_challenge_daily 直接 500。比照 delegation.ensure_schema，這張新表由服務
自己冪等建立，不受開關影響；worker 啟動時也呼叫一次。
"""

from sqlalchemy.engine import Engine

from ..models import Base, PveChallengeDaily


def ensure_schema(engine: Engine) -> None:
    """只建 PvE 每日計數表，checkfirst 保證重複啟動安全。"""
    Base.metadata.create_all(
        bind=engine,
        tables=[PveChallengeDaily.__table__],
        checkfirst=True,
    )
