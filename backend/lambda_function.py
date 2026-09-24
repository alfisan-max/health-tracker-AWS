import json, os, random
from datetime import date, timedelta
from decimal import Decimal
import boto3
from boto3.dynamodb.conditions import Key

db = boto3.resource("dynamodb")
PROFILES = db.Table(os.environ.get("PROFILES_TABLE", "Profiles"))
RECORDS = db.Table(os.environ.get("RECORDS_TABLE", "HealthRecords"))

LIMITS = {"weightKg": (20, 300), "steps": (0, 100000), "waterL": (0, 10),
          "sleepHrs": (0, 24), "calories": (0, 10000), "heartRate": (30, 220)}
NOTES = ["Morning run", "Gym workout", "Rest day", "Regular day", "Cardio", "Light workout", "Cycling"]
DEMO = [  # id, name, age, height, goal, baseline, days
    ("alex", "Alex", 21, 175, "Maintain fitness", dict(w=68, s=8000, wa=2.5, sl=7.0, c=2100, hr=71), 30),
    ("sarah", "Sarah", 22, 162, "Improve sleep and hydration", dict(w=56, s=7500, wa=2.2, sl=6.8, c=1900, hr=74), 14),
    ("rahul", "Rahul", 24, 178, "Lose weight", dict(w=82, s=6500, wa=2.4, sl=6.6, c=2400, hr=76), 30)]


def res(code, body):
    return {"statusCode": code, "headers": {"Content-Type": "application/json"},
            "body": json.dumps(body, default=lambda o: float(o) if isinstance(o, Decimal) else str(o))}


def D(x): return Decimal(str(round(x, 1)))


def seed(uid):
    for pid, name, age, h, goal, b, days in DEMO:
        PROFILES.put_item(Item={"userId": uid, "profileId": pid, "name": name, "age": age,
                                "heightCm": h, "goal": goal, "weightKg": D(b["w"])})
        with RECORDS.batch_writer() as bw:
            for i in range(days):
                d = date.today() - timedelta(days=days - 1 - i)
                note = random.choice(NOTES)
                act = note in ("Morning run", "Gym workout", "Cardio", "Cycling")
                bw.put_item(Item={
                    "profileKey": f"{uid}#{pid}", "recordDate": d.isoformat(),
                    "weightKg": D(b["w"] - i * 0.02 + random.uniform(-0.3, 0.3)),
                    "steps": int(b["s"] * random.uniform(0.85, 1.15) * (1.15 if act else 0.9)),
                    "waterL": D(min(4, max(1.5, b["wa"] + random.uniform(-0.4, 0.4)))),
                    "sleepHrs": D(min(9, max(5, b["sl"] + random.uniform(-0.6, 0.6)))),
                    "calories": int(b["c"] * random.uniform(0.93, 1.07) * (1.05 if act else 0.97)),
                    "heartRate": b["hr"] + random.randint(-3, 3), "notes": note})


def owns(uid, pid):
    return bool(pid) and "Item" in PROFILES.get_item(Key={"userId": uid, "profileId": pid})


def validate(b):
    for k, (lo, hi) in LIMITS.items():
        try:
            if not lo <= float(b[k]) <= hi: return f"{k} must be between {lo} and {hi}"
        except (KeyError, ValueError, TypeError):
            return f"{k} is missing or invalid"
    try:
        if date.fromisoformat(b["recordDate"]) > date.today(): return "recordDate cannot be in the future"
    except Exception:
        return "recordDate must be YYYY-MM-DD"


def lambda_handler(event, context):
    uid = event["requestContext"]["authorizer"]["jwt"]["claims"]["sub"]  # verified by API Gateway
    route = event["routeKey"]
    qs = event.get("queryStringParameters") or {}

    if route == "GET /profiles":
        items = PROFILES.query(KeyConditionExpression=Key("userId").eq(uid))["Items"]
        if not items:
            seed(uid)
            items = PROFILES.query(KeyConditionExpression=Key("userId").eq(uid))["Items"]
        return res(200, items)

    pid = qs.get("profile")
    if route == "GET /records":
        if not owns(uid, pid): return res(403, {"error": "Forbidden"})
        frm = (date.today() - timedelta(days=int(qs.get("days", 30)) - 1)).isoformat()
        r = RECORDS.query(KeyConditionExpression=Key("profileKey").eq(f"{uid}#{pid}") &
                          Key("recordDate").between(frm, date.today().isoformat()))
        return res(200, r["Items"])

    if route == "POST /records":
        b = json.loads(event.get("body") or "{}")
        pid = b.get("profileId")
        err = validate(b)
        if err: return res(400, {"error": err})
        if not owns(uid, pid): return res(403, {"error": "Forbidden"})
        item = {k: Decimal(str(b[k])) for k in LIMITS}
        item.update({"profileKey": f"{uid}#{pid}", "recordDate": b["recordDate"],
                     "notes": str(b.get("notes", ""))[:100]})
        RECORDS.put_item(Item=item)
        return res(200, item)

    if route == "DELETE /records/{date}":
        if not owns(uid, pid): return res(403, {"error": "Forbidden"})
        RECORDS.delete_item(Key={"profileKey": f"{uid}#{pid}", "recordDate": event["pathParameters"]["date"]})
        return res(200, {"deleted": True})

    return res(404, {"error": "Not found"})
