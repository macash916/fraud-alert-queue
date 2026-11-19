"""Policy library for the co-pilot: official text split into citable passages, plus search.

Plain English: the co-pilot must back every policy claim with a passage it can point to. This module
turns the downloaded official sources into short passages (one per numbered paragraph where the law
has them), each tagged with its source, provision, link, licence and version date, and searches them
with a mix of keyword matching (BM25) and meaning (embeddings from a small local model).

Only Open Government Licence sources are ingested (legislation.gov.uk and the ICO). FCA and PRA text
is not stored: their terms forbid putting it in a retrieval system without permission (decision V17).

Run from the repo root:
    .venv/bin/python -m src.copilot.policy_library build   # parse raw sources -> policy/passages.jsonl
    .venv/bin/python -m src.copilot.policy_library embed   # embed passages and load them into PostgreSQL
"""

from __future__ import annotations

import json
import math
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "policy" / "raw"
PASSAGES = ROOT / "policy" / "passages.jsonl"
OLLAMA = "http://127.0.0.1:11434"
EMBED_MODEL = "nomic-embed-text"
OGL = "Open Government Licence v3.0"

# Which downloaded file belongs to which source. Order matters only for readability.
LEGISLATION = [
    # (file prefix, source id, short citation stem, title, url stem)
    ("psrs_reg", "PSRs 2017", "reg", "The Payment Services Regulations 2017", "https://www.legislation.gov.uk/uksi/2017/752/regulation/"),
    ("ukgdpr_art", "UK GDPR", "Art", "UK General Data Protection Regulation", "https://www.legislation.gov.uk/eur/2016/679/article/"),
    ("sca_rts_art", "SCA RTS", "Art", "UK onshored Commission Delegated Regulation (EU) 2018/389 (SCA technical standards)", "https://www.legislation.gov.uk/eur/2018/389/article/"),
    ("sca_rts_annex", "SCA RTS", "Annex", "UK onshored Commission Delegated Regulation (EU) 2018/389 (SCA technical standards)", "https://www.legislation.gov.uk/eur/2018/389/annex"),
    ("duaa_s", "DUAA 2025", "s.", "Data (Use and Access) Act 2025", "https://www.legislation.gov.uk/ukpga/2025/18/section/"),
]
SKIP_TAGS = {"Commentaries", "Commentary", "CommentaryRef", "FootnoteRef", "Footnotes", "Metadata"}


@dataclass
class Passage:
    id: str            # stable id, e.g. "PSRs 2017 reg 76(1)"
    source: str        # e.g. "PSRs 2017"
    provision: str     # e.g. "reg 76"
    heading: str       # the provision's own heading
    text: str
    url: str
    owner: str
    licence: str
    version_date: str  # the date the text is valid from, as given by the publisher


def _local(tag: str) -> str:
    return tag.split("}")[-1]


def _text(el: ET.Element) -> str:
    """All text inside an element, skipping editorial commentary, with whitespace tidied."""
    parts: list[str] = []

    def walk(e: ET.Element) -> None:
        if _local(e.tag) in SKIP_TAGS:
            if e.tail:
                parts.append(e.tail)
            return
        name = _local(e.tag)
        if name == "Pnumber":  # sub-paragraph letters and numbers, written as "(a) "
            parts.append(f" ({''.join(e.itertext()).strip()}) ")
            if e.tail:
                parts.append(e.tail)
            return
        if e.text:
            parts.append(e.text)
        for child in e:
            walk(child)
        if name in ("td", "th"):
            parts.append(" | ")
        elif name in ("tr", "Para", "P3", "P4", "ListItem"):
            parts.append(" ")
        if e.tail:
            parts.append(e.tail)

    walk(el)
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _find(root: ET.Element, *names: str) -> ET.Element | None:
    for e in root.iter():
        if _local(e.tag) in names:
            return e
    return None


def parse_legislation(path: Path, source: str, stem: str, url: str) -> list[Passage]:
    """One passage per numbered paragraph of the provision; the whole provision if it has none."""
    root = ET.parse(path).getroot()
    valid = ""
    for e in root.iter():
        if _local(e.tag) == "valid" and e.text:
            valid = e.text.strip()
            break
    body = _find(root, "Body", "EUBody", "Schedules", "EUSchedules", "Schedule")
    if body is None:
        return []
    group = _find(body, "P1group") or body
    title_el = next((c for c in group if _local(c.tag) == "Title"), None)
    heading = _text(title_el) if title_el is not None else ""
    number = re.search(r"(\d+[A-Z]?)", path.stem.split("_")[-1])
    prov = f"{stem} {number.group(1)}" if number and stem != "Annex" else stem
    prov = prov.replace("s. ", "s.")
    paras = [e for e in group.iter() if _local(e.tag) == "P2"]
    out: list[Passage] = []
    if paras:
        for p in paras:
            num_el = next((c for c in p if _local(c.tag) == "Pnumber"), None)
            num = "".join(num_el.itertext()).strip() if num_el is not None else str(len(out) + 1)
            body_text = _text(p)
            if body_text.startswith(f"({num})"):
                body_text = body_text[len(num) + 2:].strip()
            out.append(Passage(f"{source} {prov}({num})", source, prov, heading, body_text,
                               url + (number.group(1) if number else ""), "UK legislation", OGL, valid))
    else:
        text = _text(group)
        if heading and text.startswith(heading):
            text = text[len(heading):].strip()
        out.append(Passage(f"{source} {prov}", source, prov, heading, text,
                           url + (number.group(1) if number and stem != "Annex" else ""), "UK legislation", OGL, valid))
    return [p for p in out if len(p.text) > 20]


def parse_ico(path: Path) -> list[Passage]:
    """ICO guidance saved as markdown: one passage per sub-heading, long sections split at ~180 words."""
    raw = path.read_text()
    meta, _, body = raw.partition("\n---\n")
    info = dict(line.split(": ", 1) for line in meta.splitlines() if ": " in line)
    out: list[Passage] = []
    for block in re.split(r"\n(?=#{2,4} )", body):
        lines = block.strip().splitlines()
        if not lines:
            continue
        heading = lines[0].lstrip("#").strip() if lines[0].startswith("#") else info.get("title", "")
        text = re.sub(r"\s+", " ", " ".join(lines[1:] if lines[0].startswith("#") else lines)).strip()
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # keep link text, drop link targets
        words = text.split()
        for i in range(0, len(words), 180):
            chunk = " ".join(words[i:i + 200])
            if len(chunk) > 60:
                n = len(out) + 1
                out.append(Passage(f"ICO {info.get('short', path.stem)} §{n}", "ICO", info.get("short", path.stem),
                                   heading, chunk, info.get("url", ""), "Information Commissioner's Office", OGL,
                                   info.get("published", "")))
    return out


def build() -> list[Passage]:
    passages: list[Passage] = []
    for prefix, source, stem, _title, url in LEGISLATION:
        for f in sorted((RAW / "legislation").glob(f"{prefix}*.xml")):
            passages += parse_legislation(f, source, stem, url)
    for f in sorted((RAW / "ico").glob("*.md")):
        passages += parse_ico(f)
    # DUAA s.80 only substitutes the new Articles 22A to 22D, which are already in the library as UK GDPR
    # text. Keep its opening words (what it replaced and when) and drop the repeated articles.
    duaa = [p for p in passages if p.source == "DUAA 2025"]
    passages = [p for p in passages if p.source != "DUAA 2025"]
    if duaa:
        first = duaa[0]
        first.text = first.text.split("Section 4A")[0].strip()
        first.id = f"{first.source} {first.provision}(1)"
        passages.append(first)
    ids = [p.id for p in passages]
    dupes = {i for i in ids if ids.count(i) > 1}
    assert not dupes, f"duplicate passage ids: {sorted(dupes)}"
    PASSAGES.write_text("".join(json.dumps(asdict(p)) + "\n" for p in passages))
    return passages


def load() -> list[Passage]:
    return [Passage(**json.loads(line)) for line in PASSAGES.read_text().splitlines()]


# ---------- search ----------

_TOKEN = re.compile(r"[a-z0-9£$]+")
_STOP = set("the a an of to and or in on for is are be by with that this it as at from any not which may must if "
            "under where who what when can does do has have its their they such other than into".split())


def tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]


class BM25:
    """Keyword scoring: rewards passages that share the question's rarer words."""

    def __init__(self, docs: list[str], k1: float = 1.4, b: float = 0.75):
        self.docs = [tokens(d) for d in docs]
        self.k1, self.b = k1, b
        self.avg = sum(map(len, self.docs)) / max(1, len(self.docs))
        df = Counter(t for d in self.docs for t in set(d))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def scores(self, query: str) -> list[float]:
        q = tokens(query)
        out = []
        for d in self.docs:
            tf = Counter(d)
            s = 0.0
            for t in q:
                if t in tf:
                    s += self.idf[t] * tf[t] * (self.k1 + 1) / (tf[t] + self.k1 * (1 - self.b + self.b * len(d) / self.avg))
            out.append(s)
        return out


def embed(texts: list[str], kind: str) -> list[list[float]]:
    """Embeddings from the local model; nothing leaves the machine. kind is 'document' or 'query'."""
    body = json.dumps({"model": EMBED_MODEL, "input": [f"search_{kind}: {t}" for t in texts]}).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/embed", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)["embeddings"]


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def _minmax(xs: list[float]) -> list[float]:
    lo, hi = min(xs), max(xs)
    return [0.0 if hi == lo else (x - lo) / (hi - lo) for x in xs]


# Everyday banking words -> the words the law uses. A fixed, general list (decision V18), not tuned per
# question: analysts say "card" and "block", the PSRs say "payment instrument" and "stop the use".
GLOSSARY = {
    r"\bcards?\b": "payment instrument",
    r"\bbanks?\b": "payment service provider",
    r"\bunblock\w*": "allow the use of the payment instrument or replace it",
    r"\bblock\w*": "stop the use of the payment instrument",
    r"\bcustomers?\b": "payer payment service user",
    r"\breport\w*": "notify",
    r"\bsca\b": "strong customer authentication",
    r"£35": "maximum £35 liable losses",
    r"automated decision": "significant decision based solely on automated processing",
}


def expand(query: str) -> str:
    """Add the legal wording next to the everyday wording, so both keyword and meaning search can match."""
    extra = [legal for pattern, legal in GLOSSARY.items() if re.search(pattern, query, re.IGNORECASE)]
    return query if not extra else f"{query} ({'; '.join(extra)})"


# Which sources a question may search (decision V24). A question about a case searches only what an
# analyst works to: payment law, the SCA rules and the bank's own procedures. A governance question
# (how the bank may use automated decisions or AI) searches everything, including ICO guidance.
CASE_SOURCES = {"PSRs 2017", "SCA RTS", "Procedures"}
SCOPES = ("case", "governance")


class Library:
    """Hybrid search over the passages: half keyword score, half meaning score (both scaled 0 to 1)."""

    def __init__(self, passages: list[Passage], vectors: list[list[float]] | None, weight: float = 0.5):
        self.passages = passages
        self.vectors = vectors
        self.bm25 = BM25([f"{p.heading} {p.text}" for p in passages])
        self.weight = weight

    def search(self, query: str, k: int = 5, use_glossary: bool = True,
               scope: str = "governance") -> list[tuple[Passage, float]]:
        if scope not in SCOPES:
            raise ValueError(f"scope must be one of {SCOPES}")
        query = expand(query) if use_glossary else query
        kw = _minmax(self.bm25.scores(query))
        if self.vectors:
            qv = embed([query], "query")[0]
            sem = _minmax([_cos(qv, v) for v in self.vectors])
            score = [self.weight * a + (1 - self.weight) * b for a, b in zip(kw, sem)]
        else:
            score = kw
        keep = [i for i, p in enumerate(self.passages) if scope == "governance" or p.source in CASE_SOURCES]
        ranked = sorted(keep, key=lambda i: -score[i])[:k]
        return [(self.passages[i], score[i]) for i in ranked]


def store(passages: list[Passage], vectors: list[list[float]]) -> None:
    """Load passages and their vectors into PostgreSQL (schema policy), replacing what was there."""
    sys.path.insert(0, str(ROOT / "app"))
    import db  # the app's connection settings from .env

    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS policy")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS policy.passages (
                id text PRIMARY KEY, source text NOT NULL, provision text NOT NULL, heading text,
                text text NOT NULL, url text, owner text, licence text, version_date text,
                embedding double precision[] NOT NULL, loaded_at timestamptz NOT NULL DEFAULT now())
        """)
        cur.execute("TRUNCATE policy.passages")
        for p, v in zip(passages, vectors):
            cur.execute("""INSERT INTO policy.passages (id, source, provision, heading, text, url, owner, licence,
                           version_date, embedding) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (p.id, p.source, p.provision, p.heading, p.text, p.url, p.owner, p.licence,
                         p.version_date, v))


def from_database() -> Library:
    sys.path.insert(0, str(ROOT / "app"))
    import db

    rows = db.query("SELECT id, source, provision, heading, text, url, owner, licence, version_date, embedding "
                    "FROM policy.passages ORDER BY id")
    passages = [Passage(*r[:9]) for r in rows.itertuples(index=False)]
    return Library(passages, [list(v) for v in rows.embedding])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "build":
        ps = build()
        print(f"{len(ps)} passages from {len({p.source for p in ps})} sources -> {PASSAGES.relative_to(ROOT)}")
        for src, n in Counter(p.source for p in ps).items():
            print(f"  {src}: {n}")
    elif cmd == "embed":
        ps = load()
        vs: list[list[float]] = []
        for i in range(0, len(ps), 16):
            vs += embed([f"{p.heading}. {p.text}" for p in ps[i:i + 16]], "document")
        store(ps, vs)
        print(f"{len(ps)} passages embedded with {EMBED_MODEL} and loaded into policy.passages")
