"""The engine must give each request its own connection (see app/core/database.py)."""
import threading
from collections import Counter

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import build_engine
from app.models import Base, Mailbox, Message


def test_file_database_uses_a_real_pool(tmp_path):
    engine = build_engine(f"sqlite:///{tmp_path / 'app.db'}")
    assert not isinstance(engine.pool, StaticPool)


def test_in_memory_database_keeps_its_single_connection():
    assert isinstance(build_engine("sqlite:///:memory:").pool, StaticPool)


def test_file_database_runs_in_wal_mode(tmp_path):
    engine = build_engine(f"sqlite:///{tmp_path / 'app.db'}")
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA journal_mode")).scalar() == "wal"


def test_concurrent_requests_never_see_wrong_data(tmp_path):
    """Regression: with one shared connection this returned missing rows and None."""
    engine = build_engine(f"sqlite:///{tmp_path / 'race.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        db.add(Mailbox(email_address="race@kupay.site", password_hash="x"))
        db.commit()
        for index in range(200):
            db.add(Message(mailbox_id=1, sender="s", recipient="race@kupay.site", subject=str(index), text_body="b" * 200))
        db.commit()

    problems: Counter[str] = Counter()

    def worker(number: int) -> None:
        for step in range(60):
            try:
                with Session() as db:
                    if (step + number) % 5 == 0:
                        assert db.query(Mailbox).filter(Mailbox.id == 1).first() is not None
                        db.commit()
                    else:
                        assert len(db.query(Message).filter(Message.mailbox_id == 1).limit(50).all()) == 50
            except Exception as exc:  # noqa: BLE001 - every failure is a regression
                problems[f"{type(exc).__name__}: {exc}"[:80]] += 1

    threads = [threading.Thread(target=worker, args=(number,)) for number in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not problems, dict(problems)
