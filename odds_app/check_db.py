from sqlalchemy import inspect

from odds_app.db import engine
from odds_app import models  # noqa: F401  # Ensure model tables are registered.


def main() -> None:
    inspector = inspect(engine)
    tables = sorted(inspector.get_table_names())
    print("tables:", ", ".join(tables) if tables else "<none>")


if __name__ == "__main__":
    main()
