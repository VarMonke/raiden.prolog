"""
Fetch Raiden Shogun text from the Genshin Impact wiki and build corpus.pl.
"""

import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://genshin-impact.fandom.com/api.php"
RAW = Path(__file__).parent / "data" / "raw"
OUT = Path(__file__).parent / "corpus.pl"

PAGES = [
    "Raiden_Shogun/Voice-Overs",
    "Raiden_Shogun/Profile",
    "Raiden_Shogun/Companion",
    "Mail/Great_Fortune..._(2026-06-26)",
    "Mail/Moving_Forward..._(2024-06-26)",
    "Mail/Transformations..._(2025-06-26)",
    "Mail/Wishes..._(2023-06-26)",
]


def fetch(page: str) -> str:
    """Return wikitext for a page, cached under data/raw/."""
    cache = RAW / (page.replace("/", "__") + ".json")
    if cache.exists():
        wt = json.loads(cache.read_text())["parse"]["wikitext"]["*"]
        return wt
    url = f"{BASE}?action=parse&page={urllib.parse.quote(page)}&prop=wikitext&format=json"
    req = urllib.request.Request(url, headers={"User-Agent": "markov-corpus-builder/1.0"})
    data = json.loads(urllib.request.urlopen(req, timeout=30).read())
    cache.write_text(json.dumps(data))
    return data["parse"]["wikitext"]["*"]


# ---------------------------------------------------------------- extraction

def extract(page: str, wt: str) -> list[str]:
    """Pull raw text fragments out of a page's wikitext."""
    frags = []
    # A template-field value ends at a line starting with | } = or <, or at EOF.
    FIELD = r"(.*?)(?=\n[|}=<{]|\Z)"
    if page.endswith("Voice-Overs"):
        for m in re.finditer(r"\|vo_\d+_\d+_tx\d*\s*=\s*" + FIELD, wt, re.S):
            frags.append(m.group(1))
    elif page.endswith("Profile"):
        for sec in ("Personality", "Official Introduction", "Character Stories"):
            m = re.search(r"==" + sec + r"==\n(.*?)(?=\n==[^=])", wt, re.S)
            if m:
                body = m.group(1)
                # Character Stories: keep only the textN fields
                fields = re.findall(r"\|text\d+\s*=\s*" + FIELD, body, re.S)
                frags.extend(fields if fields else [body])
    elif page.endswith("Companion"):
        for line in wt.split("\n"):
            line = line.strip(":; ")
            if "'''Ei:'''" in line or "'''Raiden Shogun:'''" in line:
                frags.append(line.split("'''", 3)[-1])
            elif re.match(r"\{\{DIcon\|Idle\}\}", line):
                frags.append(re.sub(r"\{\{DIcon\|Idle\}\}\s*", "", line))
    elif page.startswith("Mail"):
        m = re.search(r"\|text\s*=\s*" + FIELD, wt, re.S)
        if m:
            frags.append(m.group(1))
    return [f for f in frags if f.strip()]


# ------------------------------------------------------------------ cleaning

def clean(t: str) -> str:
    t = re.sub(r"<ref[^>]*/>", " ", t)
    t = re.sub(r"<ref[^>]*>.*?</ref>", " ", t, flags=re.S)
    t = re.sub(r"<gallery.*?</gallery>", " ", t, flags=re.S)
    t = re.sub(r"<br\s*/?>", " ", t)
    t = re.sub(r"</p>\s*<p>", "\n", t)
    t = re.sub(r"</?p>", " ", t)
    t = re.sub(r"<nowiki>(.*?)</nowiki>", r"\1", t, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)  # any remaining tags
    for ent, ch in [("&mdash;", " — "), ("&nbsp;", " "), ("&quot;", '"'),
                    ("&amp;", "&"), ("&#39;", "'")]:
        t = t.replace(ent, ch)

    # links: [[target|text]] -> text, [[target]] -> target; drop File:/Category:
    prev = None
    while prev != t:
        prev = t
        t = re.sub(r"\[\[(?:File|Category|Image):[^\]]*\]\]", " ", t)
        t = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", t)
        t = re.sub(r"\[\[([^\]|]*)\]\]", r"\1", t)

    # templates: reduce innermost {{...}} repeatedly
    def repl(m):
        inner = m.group(1)
        name = inner.split("|", 1)[0].strip().lower()
        params = inner.split("|")[1:]
        if name in {"quote", "description", "not a typo", "zh", "ja", "wt",
                    "tooltip", "w"} and params:
            return " " + params[0] + " "
        if name in {"traveler"}:
            return " Traveler "
        if name in {"mc"} and params:
            return " " + params[0] + " "
        return " "  # drop everything else (audio, refs, dicon, etc.)

    prev = None
    while prev != t:
        prev = t
        t = re.sub(r"\{\{([^{}]*)\}\}", repl, t)

    t = t.replace("'''", "").replace("''", "")
    t = re.sub(r"={2,}[^=\n]*={2,}", " ", t)        # leftover == headings ==
    t = re.sub(r"\{\{|\}\}", " ", t)               # leftover template braces
    t = re.sub(r"^[;:*\s]+", "", t, flags=re.M)
    t = re.sub(r"[ \t]+", " ", t)
    return t.strip()


# --------------------------------------------------------------- tokenizing

TOKEN_RE = re.compile(r"\.\.\.|…|[A-Za-z0-9’'&]+(?:[-’'][A-Za-z0-9’']+)*|[^\w\s]")
ENDERS = {".", "!", "?", "...", "…"}
ABBREV_WORDS = {"mt", "mr", "mrs", "ms", "dr", "st", "vs", "no"}


def sentences(text: str) -> list[list[str]]:
    """Tokenize and split into sentences (end punctuation kept as a token)."""
    sents, cur = [], []
    for tok in TOKEN_RE.findall(text):
        tok = "..." if tok == "…" else tok
        cur.append(tok)
        if tok in ENDERS and not (tok == "." and len(cur) > 1
                                  and cur[-2].lower() in ABBREV_WORDS):
            sents.append(cur)
            cur = []
    if len(cur) > 1:
        sents.append(cur)
    return sents


def prolog_atom(tok: str) -> str:
    return "'" + tok.replace("\\", "\\\\").replace("'", "''") + "'"


def main() -> None:
    use_cache = "--cached" in sys.argv
    if use_cache:
        def fetch_cached(p):
            return json.loads((RAW / (p.replace("/", "__") + ".json")).read_text())["parse"]["wikitext"]["*"]
        getter = fetch_cached
    else:
        getter = fetch

    all_sents = []
    for page in PAGES:
        wt = getter(page)
        frags = extract(page, wt)
        n0 = len(all_sents)
        for f in frags:
            all_sents.extend(
                s for s in sentences(clean(f))
                if len(s) >= 2 and any(re.search(r"[A-Za-z0-9]", t) for t in s))
        print(f"{page}: {len(frags)} fragments -> {len(all_sents) - n0} sentences")

    # de-duplicate, keep order
    seen, uniq = set(), []
    for s in all_sents:
        key = tuple(s)
        if key not in seen:
            seen.add(key)
            uniq.append(s)

    with open(OUT, "w") as fh:
        fh.write("% Raiden Shogun corpus — generated by build_corpus.py\n")
        fh.write("% s([tokens]). one fact per sentence, punctuation tokenized.\n\n")
        for s in uniq:
            fh.write("s([" + ", ".join(prolog_atom(t) for t in s) + "]).\n")

    words = sum(len(s) for s in uniq)
    print(f"\nwrote {OUT.name}: {len(uniq)} sentences, {words} tokens")


if __name__ == "__main__":
    main()
