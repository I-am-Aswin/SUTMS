from flask import Flask, jsonify, request, Response
from flask_cors import CORS
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import json

import config
from models import STIXObject, Collection

app = Flask(__name__)
CORS(app)

engine = create_engine(config.SQLALCHEMY_DATABASE_URI, echo=config.SQLALCHEMY_ECHO)
Session = sessionmaker(bind=engine)


@app.route("/taxii/", methods=["GET"])
def api_root():
    data = {
        "title": "Simple TAXII-like Server",
        "description": "Minimal TAXII2-like API serving STIX2 objects from MySQL",
        "contact": None,
        "versions": ["taxii-2.1"],
    }
    return jsonify(data)


@app.route("/taxii/collections", methods=["GET"])
def list_collections():
    session = Session()
    cols = session.query(Collection).all()
    out = []
    for c in cols:
        out.append({"id": c.id, "title": c.title, "description": c.description})
    return jsonify({"collections": out})


@app.route("/taxii/collections/<collection_id>/objects", methods=["GET"])
def collection_objects(collection_id):
    """Return a STIX bundle for objects in a collection. Supports pagination via ?limit=&offset="""
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))

    session = Session()

    # ensure collection exists
    coll = session.query(Collection).filter_by(id=collection_id).first()
    if not coll:
        return jsonify({"error": "collection not found"}), 404

    q = session.query(STIXObject).filter_by(collection_id=collection_id).order_by(STIXObject.created_at.desc())
    total = q.count()
    objs = q.offset(offset).limit(limit).all()

    stix_objects = [json.loads(o.raw) for o in objs]

    bundle = {
        "type": "bundle",
        "id": f"bundle--{collection_id}",
        "objects": stix_objects,
        "total": total,
        "limit": limit,
        "offset": offset,
    }

    return Response(json.dumps(bundle, ensure_ascii=False), mimetype="application/vnd.oasis.stix+json; version=2.1")


if __name__ == "__main__":
    print("Starting server on http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000, debug=True)
