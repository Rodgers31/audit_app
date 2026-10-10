"""Independent Standards control: a child session must not roll back its caller."""
from hashlib import sha256
import json
from pathlib import Path
import platform

import sqlalchemy
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

print(json.dumps({"generated_by": str(Path(__file__).name),
                  "generator_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
                  "python": platform.python_version(),
                  "sqlalchemy": sqlalchemy.__version__}))
for mode in ("conditional_savepoint", "create_savepoint"):
    engine = create_engine("sqlite://")
    with engine.begin() as setup:
        setup.execute(text("CREATE TABLE caller_effect(id integer)"))
    with engine.connect() as connection:
        outer = connection.begin()
        connection.execute(text("INSERT INTO caller_effect VALUES (1)"))
        factory = sessionmaker(bind=connection, join_transaction_mode=mode)
        try:
            with factory.begin() as child:
                assert child.scalar(text("SELECT count(*) FROM caller_effect")) == 1
                raise RuntimeError("owned refusal control")
        except RuntimeError:
            pass
        retained = connection.scalar(text("SELECT count(*) FROM caller_effect"))
        print(json.dumps({"mode": mode, "caller_effects": retained,
                          "outer_active": outer.is_active}))
        assert retained == (1 if mode == "create_savepoint" else 0)
        if outer.is_active:
            outer.rollback()
        else:
            connection.rollback()
    engine.dispose()
