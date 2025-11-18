"""Ingest a sample STIX2 bundle from sample_data into the DB."""
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from stix2 import parse
import config
from models import STIXObject, Collection


def ingest_file(path: str, collection_id: str = "default_collection"):
    engine = create_engine(config.SQLALCHEMY_DATABASE_URI, echo=config.SQLALCHEMY_ECHO)
    Session = sessionmaker(bind=engine)
    session = Session()

    with open(path, "r", encoding="utf-8") as f:
        bundle = json.load(f)

    # validate/parse with stix2 (light validation)
    # bundle can be a dict representing a STIX bundle
    try:
        parsed = parse(bundle, allow_custom=True)
    except Exception as e:
        print("Warning: stix2 parse failed:", e)
        parsed = None

    # insert each object as raw JSON string
    for obj in bundle.get("objects", []):
        st = STIXObject(
            object_id=obj.get("id"),
            object_type=obj.get("type"),
            raw=json.dumps(obj, ensure_ascii=False),
            collection_id=collection_id,
        )
        session.add(st)

    session.commit()
    print(f"Ingested {len(bundle.get('objects', []))} objects into collection {collection_id}")


if __name__ == "__main__":
    ingest_file("sample_data/sample_bundle.json")
