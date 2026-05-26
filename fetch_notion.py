import os, json, requests
from datetime import datetime, timezone

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_DB_ID  = os.environ["NOTION_DB_ID"]

# Normaliser l'ID (avec tirets)
raw = NOTION_DB_ID.replace("-","").replace(" ","").strip()
if len(raw) == 32:
    NOTION_DB_ID = f"{raw[0:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:32]}"

print(f"Token      : {NOTION_TOKEN[:12]}...")
print(f"DB ID      : {NOTION_DB_ID}")

# Version API à jour (requise pour les bases multi-sources Notion)
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2025-09-03",
    "Content-Type": "application/json",
}

# ── Méthode 1 : query directe sur la base ───────────────────────────────────
def fetch_via_database():
    print("Méthode 1 : Database Query...")
    url = f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query"
    pages, cursor = [], None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        r = requests.post(url, headers=HEADERS, json=body)
        if not r.ok:
            print(f"  Echec ({r.status_code}) : {r.text[:300]}")
            return None
        data = r.json()
        pages.extend(data["results"])
        if not data.get("has_more"):
            break
        cursor = data["next_cursor"]
    print(f"  ✅ {len(pages)} pages trouvées via Database Query")
    return pages

# ── Méthode 2 : Search API (filtre par parent database) ─────────────────────
def fetch_via_search():
    print("Méthode 2 : Search API...")
    url = "https://api.notion.com/v1/search"
    pages, cursor = [], None
    while True:
        body = {"page_size": 100, "filter": {"property": "object", "value": "page"}}
        if cursor:
            body["start_cursor"] = cursor
        r = requests.post(url, headers=HEADERS, json=body)
        if not r.ok:
            print(f"  Echec ({r.status_code}) : {r.text[:300]}")
            return None
        data = r.json()
        # Filtrer uniquement les pages dont le parent est notre base Emplacements
        for p in data["results"]:
            parent = p.get("parent", {})
            parent_id = parent.get("database_id","").replace("-","")
            if parent_id == NOTION_DB_ID.replace("-",""):
                pages.append(p)
        if not data.get("has_more"):
            break
        cursor = data["next_cursor"]
    print(f"  ✅ {len(pages)} pages trouvées via Search")
    return pages

# ── Parser une page Notion ───────────────────────────────────────────────────
def parse_page(page):
    props = page.get("properties", {})

    def text(key):
        p = props.get(key, {})
        t = p.get("title") or p.get("rich_text") or []
        return "".join(b.get("plain_text","") for b in t).strip()

    def num(key):
        return (props.get(key) or {}).get("number")

    lat = num("latitude") or num("Latitude")
    lng = num("Longitude") or num("longitude")

    if lat is None or lng is None:
        return None

    culture_raw = props.get("Culture") or props.get("Dernière culture") or {}
    culture = ""
    if culture_raw.get("type") == "select":
        s = culture_raw.get("select")
        culture = s["name"] if s else ""

    name = text("Emplacement") or text("Name") or page["id"]

    return {
        "id":      page["id"],
        "name":    name,
        "addr":    text("Adresse") or "",
        "lat":     float(lat),
        "lng":     float(lng),
        "culture": culture,
        "notes":   text("Notes") or "",
        "waze":    text("Waze") or "",
        "url":     page["url"],
    }

# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("=== Sync Notion → data.json ===")

    # Essai méthode 1, puis méthode 2 en fallback
    pages = fetch_via_database()
    if pages is None:
        pages = fetch_via_search()
    if pages is None:
        raise RuntimeError("Impossible de récupérer les données Notion.")

    emplacements, skipped = [], []
    for p in pages:
        emp = parse_page(p)
        if emp:
            emplacements.append(emp)
        else:
            props = p.get("properties", {})
            t = props.get("Emplacement") or props.get("Name") or {}
            title = t.get("title") or []
            name = "".join(b.get("plain_text","") for b in title).strip() or p["id"]
            skipped.append(name)

    print(f"✅ {len(emplacements)} avec GPS")
    print(f"⚠️  {len(skipped)} sans GPS : {', '.join(skipped[:5])}{'...' if len(skipped)>5 else ''}")

    output = {
        "updated_at":   datetime.now(timezone.utc).isoformat(),
        "emplacements": emplacements,
        "no_gps":       skipped,
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("✅ data.json généré avec succès")

if __name__ == "__main__":
    main()
