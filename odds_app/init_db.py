from odds_app.db import Base, engine


def main() -> None:
    Base.metadata.create_all(bind=engine)
    print("Database tables initialized.")


if __name__ == "__main__":
    main()
