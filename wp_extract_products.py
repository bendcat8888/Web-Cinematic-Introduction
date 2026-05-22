import json
import os
import re
import zipfile
from collections import defaultdict


def unescape_mysql(s: str) -> str:
    out = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        i += 1
        if i >= len(s):
            break
        esc = s[i]
        if esc == "n":
            out.append("\n")
        elif esc == "r":
            out.append("\r")
        elif esc == "t":
            out.append("\t")
        else:
            out.append(esc)
        i += 1
    return "".join(out)


def parse_values(values_text: str):
    rows = []
    i = 0
    n = len(values_text)
    while i < n:
        while i < n and values_text[i] != "(":
            i += 1
        if i >= n:
            break
        i += 1

        row = []
        val = []
        in_str = False

        while i < n:
            ch = values_text[i]
            if in_str:
                if ch == "\\":
                    if i + 1 < n:
                        val.append("\\" + values_text[i + 1])
                        i += 2
                        continue
                if ch == "'":
                    in_str = False
                    i += 1
                    continue
                val.append(ch)
                i += 1
                continue

            if ch == "'":
                in_str = True
                i += 1
                continue

            if ch == ",":
                token = "".join(val).strip()
                if token.upper() == "NULL" or token == "":
                    row.append(None)
                else:
                    row.append(token)
                val = []
                i += 1
                continue

            if ch == ")":
                token = "".join(val).strip()
                if token.upper() == "NULL" or token == "":
                    row.append(None)
                else:
                    row.append(token)
                i += 1
                rows.append(row)
                break

            val.append(ch)
            i += 1

        while i < n and values_text[i] in ",\n\r \t":
            i += 1

    fixed = []
    for row in rows:
        new_row = []
        for token in row:
            if token is None:
                new_row.append(None)
            else:
                new_row.append(unescape_mysql(token))
        fixed.append(new_row)
    return fixed


def strip_tags(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s)
    s = s.replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def safe_slug(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9\-]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s


def main():
    sql_path = os.environ.get("WP_SQL") or r"D:\innogen website back_up _ feb 8 2023\wp-content\updraft\innogen-db-full.sql"
    uploads_dir = os.environ.get("WP_UPLOADS_DIR") or r"D:\innogen website back_up _ feb 8 2023\wp-content\uploads"
    uploads_zip = os.environ.get("WP_UPLOADS_ZIP") or r"D:\innogen website back_up _ feb 8 2023\wp-content\uploads.zip"
    project = os.environ.get("PROJECT_DIR") or os.path.dirname(os.path.abspath(__file__))

    out_dir = os.path.join(project, "assets", "products")
    out_img_dir = os.path.join(out_dir, "images")
    os.makedirs(out_img_dir, exist_ok=True)

    re_insert = re.compile(r"^INSERT INTO `([^`]+)` VALUES ")
    need_tables = {"wp_posts", "wp_postmeta", "wp_terms", "wp_term_taxonomy", "wp_term_relationships"}

    products_raw = {}
    thumb_of = {}
    attached_file = {}
    term = {}
    term_tax = {}
    rels = defaultdict(list)

    cur_table = None
    stmt = []

    with open(sql_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if cur_table is None:
                m = re_insert.match(line)
                if not m:
                    continue
                t = m.group(1)
                if t not in need_tables:
                    continue
                cur_table = t
                stmt = [line]
                if not line.rstrip().endswith(";"):
                    continue
            else:
                stmt.append(line)

            if not stmt[-1].rstrip().endswith(";"):
                continue

            full = "".join(stmt)
            parts = full.split(" VALUES ", 1)
            if len(parts) != 2:
                cur_table = None
                stmt = []
                continue
            values_part = parts[1].strip()
            if values_part.endswith(";"):
                values_part = values_part[:-1]
            rows = parse_values(values_part)

            if cur_table == "wp_posts":
                for r in rows:
                    if len(r) < 21:
                        continue
                    try:
                        pid = int(r[0])
                    except Exception:
                        continue
                    post_content = r[4] or ""
                    post_title = r[5] or ""
                    post_status = r[7] or ""
                    post_name = r[11] or ""
                    guid = r[18] or ""
                    post_type = r[20] or ""
                    if post_type != "al_product" or post_status != "publish":
                        continue
                    products_raw[pid] = {
                        "id": pid,
                        "title": post_title.strip(),
                        "slug": post_name.strip() or str(pid),
                        "guid": guid.strip(),
                        "content": post_content,
                    }

            elif cur_table == "wp_postmeta":
                for r in rows:
                    if len(r) < 4:
                        continue
                    try:
                        post_id = int(r[1])
                    except Exception:
                        continue
                    meta_key = (r[2] or "").strip()
                    meta_value = r[3]
                    if meta_key == "_thumbnail_id" and meta_value:
                        try:
                            thumb_of[post_id] = int(meta_value)
                        except Exception:
                            pass
                    elif meta_key == "_wp_attached_file" and meta_value:
                        attached_file[post_id] = str(meta_value).strip()

            elif cur_table == "wp_terms":
                for r in rows:
                    if len(r) < 3:
                        continue
                    try:
                        tid = int(r[0])
                    except Exception:
                        continue
                    term[tid] = {"name": (r[1] or "").strip(), "slug": (r[2] or "").strip()}

            elif cur_table == "wp_term_taxonomy":
                for r in rows:
                    if len(r) < 3:
                        continue
                    try:
                        ttid = int(r[0])
                        tid = int(r[1])
                    except Exception:
                        continue
                    taxonomy = (r[2] or "").strip()
                    term_tax[ttid] = {"term_id": tid, "taxonomy": taxonomy}

            elif cur_table == "wp_term_relationships":
                for r in rows:
                    if len(r) < 2:
                        continue
                    try:
                        obj_id = int(r[0])
                        ttid = int(r[1])
                    except Exception:
                        continue
                    rels[obj_id].append(ttid)

            cur_table = None
            stmt = []

    label_patterns = {
        "brand": re.compile(r"Brand Name:\s*(.+?)\s*(?:Generic Name:|Pharmaceutical Category:|Dosage Strength:|Dosage Form:|\*Disclaimer|$)", re.I | re.S),
        "generic": re.compile(r"Generic Name:\s*(.+?)\s*(?:Pharmaceutical Category:|Dosage Strength:|Dosage Form:|\*Disclaimer|$)", re.I | re.S),
        "therapeuticClass": re.compile(r"Pharmaceutical Category:\s*(.+?)\s*(?:Dosage Strength:|Dosage Form:|\*Disclaimer|$)", re.I | re.S),
        "strength": re.compile(r"Dosage Strength:\s*(.+?)\s*(?:Dosage Form:|\*Disclaimer|$)", re.I | re.S),
        "form": re.compile(r"Dosage Form:\s*(.+?)\s*(?:\*Disclaimer|$)", re.I | re.S),
    }
    href_re = re.compile(r'href=["\']([^"\']+)["\']', re.I)

    zip_obj = zipfile.ZipFile(uploads_zip) if os.path.exists(uploads_zip) else None

    category_to_products = defaultdict(list)
    out_products = {}
    copied_images = 0
    missing_images = 0

    for pid, p in sorted(products_raw.items()):
        content = p.get("content") or ""
        plain = strip_tags(content)

        details = {}
        for k, rx in label_patterns.items():
            m = rx.search(plain)
            details[k] = m.group(1).strip(" \t\r\n:") if m else ""

        dl = ""
        for m in href_re.finditer(content):
            url = m.group(1)
            if any(h in url.lower() for h in ("mediafire.com", "drive.google.com", ".pdf")):
                dl = url
                break

        cats = []
        for ttid in rels.get(pid, []):
            tx = term_tax.get(ttid)
            if not tx or tx.get("taxonomy") != "al_product-cat":
                continue
            tinfo = term.get(tx["term_id"])
            if not tinfo:
                continue
            cats.append({"slug": tinfo["slug"], "name": tinfo["name"]})
            category_to_products[tinfo["slug"]].append(pid)

        img_rel = ""
        thumb_id = thumb_of.get(pid)
        if thumb_id:
            img_rel = attached_file.get(thumb_id, "") or ""

        out_img = ""
        if img_rel:
            ext = os.path.splitext(img_rel)[1].lower() or ".png"
            sslug = safe_slug(p.get("slug") or str(pid)) or str(pid)
            out_img = f"assets/products/images/{sslug}{ext}"
            dest_path = os.path.join(project, out_img.replace("/", os.sep))

            if not os.path.exists(dest_path):
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                src_path = os.path.join(uploads_dir, img_rel.replace("/", os.sep))
                copied = False
                if os.path.exists(src_path):
                    with open(src_path, "rb") as rf, open(dest_path, "wb") as wf:
                        wf.write(rf.read())
                    copied = True
                elif zip_obj is not None:
                    member = "uploads/" + img_rel
                    try:
                        data = zip_obj.read(member)
                        with open(dest_path, "wb") as wf:
                            wf.write(data)
                        copied = True
                    except KeyError:
                        copied = False

                if copied:
                    copied_images += 1
                else:
                    missing_images += 1
                    out_img = ""

        out_products[pid] = {
            "id": pid,
            "title": p.get("title", ""),
            "slug": p.get("slug", "") or str(pid),
            "brand": details["brand"],
            "generic": details["generic"],
            "therapeuticClass": details["therapeuticClass"],
            "strength": details["strength"],
            "form": details["form"],
            "downloadUrl": dl,
            "categories": cats,
            "image": out_img,
        }

    if zip_obj is not None:
        zip_obj.close()

    categories = {}
    for slug, ids in category_to_products.items():
        name = ""
        for pid in ids:
            for c in out_products[pid]["categories"]:
                if c["slug"] == slug:
                    name = c["name"]
                    break
            if name:
                break
        categories[slug] = {"slug": slug, "name": name or slug, "count": len(ids), "productIds": ids}

    out = {
        "generatedFrom": os.path.basename(sql_path),
        "productCount": len(out_products),
        "categories": categories,
        "products": list(out_products.values()),
        "copiedImages": copied_images,
        "missingImages": missing_images,
    }

    json_path = os.path.join(out_dir, "products.json")
    with open(json_path, "w", encoding="utf-8") as wf:
        json.dump(out, wf, ensure_ascii=False, indent=2)

    print("Products:", len(out_products))
    print("Categories:", len(categories))
    print("Wrote:", json_path)
    print("Copied images:", copied_images)
    print("Missing images:", missing_images)


if __name__ == "__main__":
    main()
