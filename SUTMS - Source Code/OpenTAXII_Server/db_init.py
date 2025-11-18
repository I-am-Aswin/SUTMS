"""Create DB tables and a default collection."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, Collection
import config


def init_db():
    engine = create_engine(config.SQLALCHEMY_DATABASE_URI, echo=config.SQLALCHEMY_ECHO)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # ensure a default collection exists
    qc = session.query(Collection).filter_by(id="default_collection").first()
    if not qc:
        default = Collection(
            id="default_collection",
            title="Default Collection",
            description="Default collection for STIX objects",
        )
        session.add(default)
        session.commit()
        print("Created default_collection")
    else:
        print("default_collection already exists")


if __name__ == "__main__":
    init_db()
