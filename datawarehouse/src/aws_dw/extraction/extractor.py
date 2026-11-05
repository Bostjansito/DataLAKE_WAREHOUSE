"""Batch-scoped source capture. Published manifests and payloads are immutable."""
import base64
import csv
import hashlib
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from tempfile import TemporaryFile
from uuid import uuid4

import boto3
import pymysql
from bson import json_util
from pymongo import MongoClient

MYSQL_COLUMNS = {
    "customers": ["customer_id", "name", "email", "phone", "city", "department", "registration_date", "updated_at"],
    "products": ["product_id", "name", "category", "price", "description", "is_active", "updated_at"],
    "orders": ["order_id", "customer_id", "order_date", "status", "sales_channel", "payment_method", "total"],
    "order_items": ["order_item_id", "order_id", "product_id", "quantity", "unit_price", "subtotal"],
}
MONGO_COLUMNS = {
    "reviews": ["review_id", "customer_id", "product_id", "rating", "reviewed_at", "document_json"],
    "navigation_events": ["event_id", "event_type", "occurred_at", "customer_id", "product_id", "sales_channel", "document_json"],
}


def validate_batch_id(batch_id):
    value = str(batch_id)
    if not value.isascii() or not value.isdecimal() or str(int(value)) != value or not 0 <= int(value) <= 365:
        raise ValueError("batch_id must be canonical integer 0 (initial) or 1..365 (DE-DW daily batch)")
    return value


def get_mysql_connection(streaming=True):
    try:
        if not os.environ.get("MYSQL_SSL_CA"):
            raise ValueError("MYSQL_SSL_CA is required")
        return pymysql.connect(
            host=os.environ["MYSQL_HOST"], port=int(os.getenv("MYSQL_PORT", "3306")),
            user=os.environ["MYSQL_USER"], password=os.environ["MYSQL_PASSWORD"],
            database=os.environ["MYSQL_DATABASE"], charset="utf8mb4", autocommit=False,
            cursorclass=pymysql.cursors.SSCursor if streaming else pymysql.cursors.Cursor,
            ssl_ca=os.environ["MYSQL_SSL_CA"], ssl_verify_cert=True, ssl_verify_identity=True,
            connect_timeout=15,
        )
    except Exception:
        raise RuntimeError("Unable to connect to MySQL with verified TLS") from None


def get_mongo_client():
    try:
        if not os.environ.get("MONGO_TLS_CA_FILE"):
            raise ValueError("MONGO_TLS_CA_FILE is required")
        return MongoClient(
            os.environ["MONGO_URI"], tls=True,
            tlsCAFile=os.environ["MONGO_TLS_CA_FILE"],
            tlsAllowInvalidCertificates=False, tlsAllowInvalidHostnames=False,
            retryWrites=False, tz_aware=True, serverSelectionTimeoutMS=15000,
        )
    except Exception:
        raise RuntimeError("Unable to configure MongoDB with verified TLS") from None


def s3_client():
    return boto3.client("s3", region_name=os.environ["AWS_REGION"])


def manifest_key(source, batch_id):
    return f"raw/{source}/batch_id={validate_batch_id(batch_id)}/manifest.json"


def read_manifest(source, batch_id, s3=None, optional=False):
    s3 = s3 or s3_client()
    try:
        result = s3.get_object(Bucket=os.environ["S3_BUCKET"], Key=manifest_key(source, batch_id))
    except s3.exceptions.NoSuchKey:
        if optional:
            return None
        raise
    with result["Body"] as body:
        manifest = json.load(body)
    if manifest["batch_id"] != validate_batch_id(batch_id) or manifest["source"] != source:
        raise ValueError("Manifest identity mismatch")
    return manifest


def _value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _payload(s3, source, entity, batch_id, columns, rows):
    # Unique capture paths permit recovery after an interrupted, unpublished capture.
    key = f"raw/{source}/{entity}/batch_id={batch_id}/{uuid4().hex}/data.csv"
    import io
    with TemporaryFile(mode="w+b") as binary:
        text = io.TextIOWrapper(binary, encoding="utf-8", newline="", write_through=True)
        writer = csv.writer(text)
        writer.writerow(columns)
        count = 0
        for row in rows:
            writer.writerow([_value(value) for value in row])
            count += 1
        text.flush()
        binary.seek(0)
        hasher = hashlib.sha256()
        while chunk := binary.read(1024 * 1024):
            hasher.update(chunk)
        digest = hasher.digest()
        size = binary.tell()
        binary.seek(0)
        s3.put_object(Bucket=os.environ["S3_BUCKET"], Key=key, Body=binary,
                      ContentLength=size, ContentType="text/csv", IfNoneMatch="*",
                      ChecksumSHA256=base64.b64encode(digest).decode())
        text.detach()
    return {"key": key, "rows": count, "columns": columns, "bytes": size,
            "sha256": digest.hex(), "s3_uri": f"s3://{os.environ['S3_BUCKET']}/{key}"}


def _capture(source, batch_id, extract):
    batch_id = validate_batch_id(batch_id)
    s3 = s3_client()
    existing = read_manifest(source, batch_id, s3, optional=True)
    if existing is not None:
        return existing
    manifest = {"version": 1, "batch_id": batch_id, "source": source,
                "extracted_at": datetime.now(timezone.utc).isoformat(),
                "mode": "initial" if batch_id == "0" else "incremental",
                "selection": "all rows" if batch_id == "0" else "dimensions full; fact IDs base + batch_id*10 through +2 (DE-DW append_batch)",
                "entities": {}}
    extract(s3, manifest)
    if batch_id != "0":
        facts = ("orders", "order_items") if source == "mysql" else tuple(MONGO_COLUMNS)
        if any(manifest["entities"][entity]["rows"] != 3 for entity in facts):
            raise ValueError("Incomplete DE-DW daily batch; run append --batch-id N before capture")
    body = json.dumps(manifest, sort_keys=True).encode()
    # A competing capture fails visibly rather than replacing the published batch.
    s3.put_object(Bucket=os.environ["S3_BUCKET"], Key=manifest_key(source, batch_id),
                  Body=body, ContentType="application/json", IfNoneMatch="*",
                  ChecksumSHA256=base64.b64encode(hashlib.sha256(body).digest()).decode())
    return manifest


def extract_mysql_to_s3(batch_id):
    def extract(s3, manifest):
        conn = get_mysql_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                cur.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")
            for entity, columns in MYSQL_COLUMNS.items():
                with conn.cursor() as cur:
                    query = f"SELECT {', '.join(columns)} FROM {entity}"
                    params = ()
                    if manifest["batch_id"] != "0" and entity in ("orders", "order_items"):
                        base = 1_000_000 if entity == "orders" else 10_000_000
                        start = base + int(manifest["batch_id"]) * 10
                        query += f" WHERE {columns[0]} >= %s AND {columns[0]} < %s"
                        params = (start, start + 3)
                    cur.execute(query + f" ORDER BY {columns[0]}", params)
                    def rows():
                        while chunk := cur.fetchmany(1000):
                            yield from chunk
                    manifest["entities"][entity] = _payload(s3, "mysql", entity, manifest["batch_id"], columns, rows())
        finally:
            conn.close()
    return _capture("mysql", batch_id, extract)


def _flatten(entity, doc):
    customer, product = doc.get("customer") or {}, doc.get("product") or {}
    document = json_util.dumps(doc, json_options=json_util.RELAXED_JSON_OPTIONS)
    if entity == "reviews":
        return (doc.get("review_id"), customer.get("customer_id"), product.get("product_id"),
                doc.get("rating"), doc.get("reviewed_at"), document)
    return (doc.get("event_id"), doc.get("event_type"), doc.get("occurred_at"),
            customer.get("customer_id"), product.get("product_id"),
            (doc.get("device") or {}).get("sales_channel"), document)


def extract_mongo_to_s3(batch_id):
    def extract(s3, manifest):
        client = get_mongo_client()
        try:
            db = client[os.environ["MONGO_DATABASE"]]
            for entity, columns in MONGO_COLUMNS.items():
                query = {}
                if manifest["batch_id"] != "0":
                    start = 1_000_000 + int(manifest["batch_id"]) * 10
                    query = {columns[0]: {"$gte": start, "$lt": start + 3}}
                with db[entity].find(query).sort(columns[0], 1).batch_size(1000) as cursor:
                    manifest["entities"][entity] = _payload(
                        s3, "mongodb", entity, manifest["batch_id"], columns,
                        (_flatten(entity, doc) for doc in cursor))
        finally:
            client.close()
    return _capture("mongodb", batch_id, extract)


def verify_payload(s3, info):
    digest = hashlib.sha256()
    result = s3.get_object(Bucket=os.environ["S3_BUCKET"], Key=info["key"])
    size = 0
    with result["Body"] as body:
        for chunk in body.iter_chunks(chunk_size=1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    if digest.hexdigest() != info["sha256"] or size != info["bytes"]:
        raise ValueError(f"S3 payload integrity failure: {info['key']}")
