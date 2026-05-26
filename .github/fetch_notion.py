import os, json, requests
from datetime import datetime, timezone

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_DB_ID  = os.environ["NOTION_DB_ID"]

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

def fetch_all_pages():
    url = f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query"
    pages, cursor = [], None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        r = requests.post(url, headers=HEADERS, json=body)
        r.raise_for_status()
        data = r.json()
        pages.extend(data["results"])
        if not data.get("has_more"):
            break
        cursor = data["next_cursor"]
    return pages

def parse_page(page):
    props = page["properties"]

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

def main():
    print("Fetching Notion database...")
    pages = fetch_all_pages()
    print(f"{len(pages)} pages trouvées")

    emplacements, skipped = [], []
    for p in pages:
        emp = parse_page(p)
        if emp:
            emplacements.append(emp)
        else:
            props = p["properties"]
            t = (props.get("Emplacement") or props.get("Name") or {})
            title = t.get("title") or []
            name = "".join(b.get("plain_text","") for b in title) or p["id"]
            skipped.append(name)

    print(f"✅ {len(emplacements)} avec GPS, ⚠️ {len(skipped)} sans GPS")

    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "emplacements": emplacements,
        "no_gps": skipped,
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("✅ data.json généré")

if __name__ == "__main__":
    main()
