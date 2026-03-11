from odds_app.db import Base, engine
from odds_app import models  # noqa: F401  # Ensure models are registered on metadata.


def main() -> None:
    Base.metadata.create_all(bind=engine)
    print("Database tables initialized.")


if __name__ == "__main__":
    main()
