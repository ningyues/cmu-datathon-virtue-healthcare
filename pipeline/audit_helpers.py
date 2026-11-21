"""Run the facility export and PIN checks locally, using the Python standard library."""
import ast
import csv
from io import TextIOWrapper
from math import asin, cos, isfinite, radians, sin, sqrt
import re

FIELDS = ("description", "specialties", "procedure", "equipment", "capability", "capacity")
NIL = {"", "null", "n/a", "na", "unknown"}
UUID_RE = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", re.I)
ALIASES = {"nctofdelhi":"delhi", "nctdelhi":"delhi", "nationalcapitalterritoryofdelhi":"delhi",
           "chattisgarh":"chhattisgarh", "telengana":"telangana", "orissa":"odisha",
           "pondicherry":"puducherry", "uttaranchal":"uttarakhand"}


def clean(s):
    return "" if s.strip().lower() in NIL else s.strip()


def compact(s):
    return re.sub(r"[\s.\-]+", "", clean(s).lower())


def state(s):
    key = compact(s.split(",")[-1])
    return ALIASES.get(key, key)


def point(a, b):
    try:
        lat, lon = float(a), float(b)
    except (ValueError, TypeError):
        return None
    if isfinite(lat) and isfinite(lon) and 6 <= lat <= 38 and 68 <= lon <= 98:
        return lat, lon
    return None


def km(a, b):
    x, y, u, v = map(radians, (*a, *b))
    h = sin((x-u)/2)**2 + cos(x)*cos(u)*sin((y-v)/2)**2
    return 12742.0176 * asin(sqrt(min(1, max(0, h))))


def export_rows(z, name):
    with z.open(name) as f, TextIOWrapper(f, encoding="utf-8-sig", newline="") as text:
        reader = csv.reader(text, strict=True)
        header = next(reader)
        if len(set(header)) != len(header) or not set(("unique_id","name",*FIELDS)) <= set(header):
            raise ValueError("The CSV is missing required fields or has duplicate column names")
        last_line = reader.line_num
        rows = []
        for values in reader:
            if len(values) != len(header):
                raise ValueError(f"Unexpected CSV field count at physical line {reader.line_num}")
            rows.append((dict(zip(header, values)), last_line + 1, reader.line_num))
            last_line = reader.line_num
    return header, rows


def evidence(z):
    """Read only data literals from the exported notebooks; never execute their code."""
    src = z.read("Datathon/Datathon/facility_evidence_audit.py").decode("utf-8-sig")
    seeds = {}
    for stmt in ast.parse(src).body:
        if isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Name):
            name = stmt.targets[0].id
            if name in {"postal_rows", "field_rows", "reference_date"}:
                seeds[name] = ast.literal_eval(stmt.value)
    postal = {tuple(e[:4]): e[4:] for e in seeds["postal_rows"]}
    guards = {k[0]: k for k in postal}
    facts = {}
    for uid, col, claim, verdict, url, note in seeds["field_rows"]:
        facts[(guards[uid], col, claim)] = (verdict, url, note, seeds["reference_date"])
    # The older SQL notebook also records a named Level III NICU finding.
    # Bind it to the exact branch and SQL evidence tuple; the other SQL finding overlaps the Python notebook.
    sql = z.read("Datathon/Datathon/Datathon-Data Clearning.sql").decode("utf-8-sig")
    branch = ("fac0cc70-81a9-462d-bced-5ca40257b027","Sanjivani Multi Speciality Hospital",
              "Chengannur","Kollakadavu")
    pattern = (r"'"+branch[0]+r"',\s*'capability',\s*'NICU Level III',\s*'official_page_supports',"
               r"\s*'([^']+)',\s*'([^']+)',\s*DATE\s*'([0-9-]+)'")
    match = re.search(pattern, sql)
    if match:
        facts[(branch,"capability","NICU Level III")] = ("official_page_supports", *match.groups())
    return postal, facts


def table(path, fields, rows):
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        w = csv.writer(f)
        w.writerow(fields)
        w.writerows(rows)

