"""Generate and ingest a large number of demo IoC STIX objects into the DB.

Usage examples (PowerShell):

# generate 1000 IoCs into default_collection
python ingest_feeds.py --count 1000

# generate 500 in a named collection
python ingest_feeds.py --count 500 --collection demo_collection

# tune batch commit size
python ingest_feeds.py --count 2000 --batch 500

This script does not require Docker to run (but DB must be available per `config.py`).
"""
import argparse
import json
import random
import uuid
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import config
from models import STIXObject, Collection


def make_indicator(i: int):
    # choose pattern type randomly
    kind = random.choice(["ipv4", "domain", "file_hash", "url"])
    uid = str(uuid.uuid4())
    if kind == "ipv4":
        octet = (i % 250) + 1
        pattern = f"[ipv4-addr:value = '198.51.100.{octet}']"
        title = f"Malicious IP 198.51.100.{octet}"
    elif kind == "domain":
        pattern = f"[domain-name:value = 'malicious{(i % 1000)}.example.com']"
        title = f"Malicious domain malicious{(i % 1000)}.example.com"
    elif kind == "file_hash":
        # fake sha256-ish hex
        fake_hash = uuid.uuid4().hex + uuid.uuid4().hex[:32]
        pattern = f"[file:hashes.'SHA-256' = '{fake_hash}']"
        title = f"Malicious file {fake_hash[:8]}"
    else:
        pattern = f"[url:value = 'http://malicious.example.com/{i}']"
        title = f"Malicious URL http://malicious.example.com/{i}"

    return {
        "type": "indicator",
        "id": f"indicator--{uid}",
        "created": datetime.now(timezone.utc).isoformat(),
        "modified": datetime.now(timezone.utc).isoformat(),
        "name": title,
        "pattern": pattern,
        "pattern_type": "stix",
        "valid_from": datetime.now(timezone.utc).isoformat(),
    }


def make_malware(i: int):
    uid = str(uuid.uuid4())
    return {
        "type": "malware",
        "id": f"malware--{uid}",
        "created": datetime.now(timezone.utc).isoformat(),
        "modified": datetime.now(timezone.utc).isoformat(),
        "name": f"DemoMalware-{i % 1000}",
        "is_family": False,
    }


def make_attack_pattern(i: int):
    uid = str(uuid.uuid4())
    return {
        "type": "attack-pattern",
        "id": f"attack-pattern--{uid}",
        "created": datetime.now(timezone.utc).isoformat(),
        "modified": datetime.now(timezone.utc).isoformat(),
        "name": f"Example Attack Pattern {(i % 200)}",
    }


def make_object(i: int):
    # distribute types so we have variety
    r = i % 10
    if r < 6:
        return make_indicator(i)
    elif r < 8:
        return make_malware(i)
    else:
        return make_attack_pattern(i)


def ensure_collection(session, collection_id: str):
    coll = session.query(Collection).filter_by(id=collection_id).first()
    if not coll:
        coll = Collection(id=collection_id, title=f"{collection_id}", description="Demo collection")
        session.add(coll)
        session.commit()
        print(f"Created collection '{collection_id}'")
    return coll


def ingest(count: int, collection_id: str, batch: int = 200):
    engine = create_engine(config.SQLALCHEMY_DATABASE_URI, echo=config.SQLALCHEMY_ECHO)
    Session = sessionmaker(bind=engine)
    session = Session()

    ensure_collection(session, collection_id)

    to_commit = []
    total_inserted = 0

    for i in range(1, count + 1):
        obj = make_object(i)
        st = STIXObject(
            object_id=obj.get("id"),
            object_type=obj.get("type"),
            raw=json.dumps(obj, ensure_ascii=False),
            collection_id=collection_id,
        )
        session.add(st)
        total_inserted += 1

        if total_inserted % batch == 0:
            session.commit()
            print(f"Committed {total_inserted} objects so far...")

    # final commit
    session.commit()
    print(f"Ingestion complete: {total_inserted} objects inserted into collection '{collection_id}'")


def main():
    parser = argparse.ArgumentParser(description="Generate and ingest demo STIX IoC objects into the DB")
    parser.add_argument("--count", type=int, default=1000, help="Number of objects to generate (default 1000)")
    parser.add_argument("--collection", type=str, default="default_collection", help="Target collection id")
    parser.add_argument("--batch", type=int, default=200, help="Batch commit size")

    args = parser.parse_args()

    print(f"Connecting to DB at: {config.SQLALCHEMY_DATABASE_URI}")
    print(f"Will insert {args.count} objects into collection '{args.collection}' with batch={args.batch}")

    ingest(args.count, args.collection, args.batch)


if __name__ == "__main__":
    main()
