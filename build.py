#!/usr/bin/env python3
"""
Сборка библиотеки RoboCup Soccer.

  python3 build.py                 скачать всё, что можно, и пересобрать README.md + MANUAL_DOWNLOAD.md
  python3 build.py --no-download   только пересобрать индекс (например, после ручного скачивания)
  python3 build.py --folder 50_ssl скачать только одну папку

Логика индекса:
  * файл лежит в репозитории      -> в README ссылка на локальный файл;
  * файла нет                     -> в README ссылка на оригинал;
  * файл не скачался / Google Drive -> дополнительно попадает в MANUAL_DOWNLOAD.md.

Ручное скачивание: сохраните файл ровно под тем именем и в ту папку, что указаны в
MANUAL_DOWNLOAD.md, и запустите `python3 build.py --no-download`. Ссылка в README станет локальной.
Файлы с Google Drive без известного имени кладите в папку _manual_drive/ (они попадут в README автоматически).
"""
import argparse
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LINKS = ROOT / "links.txt"
MANUAL_DIR = ROOT / "_manual_drive"

MACROS = {
    "{RCJ}": "https://robocup-junior.github.io",
    "{EU26}": "https://raw.githubusercontent.com/robocup-junior/rcj-eu-soccer-tdp-2026/main",
    "{B2025}": "https://raw.githubusercontent.com/robocup-junior/rcj-soccer-tdp-2025/master",
}

FOLDER_TITLES = OrderedDict([
    ("01_rcj_infrared_lightweight", "RCJ Soccer Infrared / Lightweight: TDP и постеры"),
    ("02_rcj_entry", "RCJ Soccer Entry (1:1 Infrared, 1:1 Standard Kit)"),
    ("03_rcj_open_vision", "RCJ Soccer Open / Vision (зрение, омни-камеры)"),
    ("04_rcj_papers_sim", "Научные статьи по RCJ и симуляция RCJ"),
    ("05_rcj_blogs_code", "Блоги, код и CAD команд RCJ (только ссылки)"),
    ("50_ssl", "Small Size League"),
    ("51_msl", "Middle Size League"),
    ("52_spl", "Standard Platform League"),
    ("53_humanoid", "Humanoid League"),
    ("54_simulation", "Simulation 2D / 3D"),
    ("60_game_ai", "Игровые алгоритмы и ИИ (стратегия, пасы, RL; в основном SSL)"),
])

DRIVE_RE = re.compile(r"https?://(?:drive|docs)\.google\.com/[^\s)>\]\"'<]+")
UA = "Mozilla/5.0 (X11; Linux x86_64) robocup-library-builder/1.0"


def expand(s):
    for k, v in MACROS.items():
        s = s.replace(k, v)
    return s.strip()


def normalize(url):
    """GitHub blob -> raw, arXiv abs -> pdf."""
    m = re.match(r"https://github\.com/([^/]+)/([^/]+)/blob/(.+)", url)
    if m:
        return f"https://raw.githubusercontent.com/{m.group(1)}/{m.group(2)}/{m.group(3)}"
    return re.sub(r"arxiv\.org/abs/", "arxiv.org/pdf/", url)


def is_drive(url):
    return bool(DRIVE_RE.match(url))


def read_entries():
    entries = []
    for ln, line in enumerate(LINKS.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 6:
            print(f"[!] links.txt:{ln}: ожидалось 6 полей, найдено {len(parts)} — строка пропущена", file=sys.stderr)
            continue
        folder, fname, title, tags, page, furl = parts
        entries.append({
            "folder": folder, "filename": fname, "title": title, "tags": tags,
            "page": expand(page), "file_url": expand(furl),
        })
    return entries


def download(url, dest, expect_pdf):
    """Возвращает (ok, причина)."""
    url = normalize(url)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:  # сеть, SSL, таймаут
        return False, f"{type(e).__name__}: {e}"
    if expect_pdf and not data.lstrip()[:5].startswith(b"%PDF"):
        return False, "ответ не является PDF (вероятно, HTML-страница, вход или защита от ботов)"
    if not data:
        return False, "пустой ответ"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(data)
    tmp.replace(dest)
    return True, ""


def rel_link(path):
    return urllib.parse.quote(path.relative_to(ROOT).as_posix())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-download", action="store_true", help="не скачивать, только пересобрать индекс")
    ap.add_argument("--folder", help="скачивать только эту папку (например 50_ssl)")
    ap.add_argument("--delay", type=float, default=1.0, help="пауза между загрузками, сек")
    args = ap.parse_args()

    entries = read_entries()
    manual = []   # {title, url, folder, filename, reason}
    drive_extra = []  # ссылки на Google Drive, найденные внутри скачанных .md

    for e in entries:
        e["dest"] = ROOT / e["folder"] / e["filename"] if e["filename"] else None
        e["status"] = "link"  # link | local
        if not e["file_url"]:
            continue
        dest = e["dest"]
        if dest.exists() and dest.stat().st_size > 0:
            e["status"] = "local"
            continue
        if args.no_download or (args.folder and e["folder"] != args.folder):
            manual.append({**e, "url": e["file_url"], "reason": "ещё не скачано"})
            continue
        if is_drive(e["file_url"]):
            manual.append({**e, "url": e["file_url"], "reason": "Google Drive: автоматически не скачивается"})
            continue
        print(f"GET  {e['file_url']}")
        ok, reason = download(e["file_url"], dest, dest.suffix.lower() == ".pdf")
        if ok:
            e["status"] = "local"
            print(f"  ok -> {dest.relative_to(ROOT)}")
        else:
            print(f"  FAIL: {reason}")
            manual.append({**e, "url": e["file_url"], "reason": reason})
        time.sleep(args.delay)

    # Ссылки на Google Drive внутри скачанных markdown-анкет команд
    seen = set()
    for e in entries:
        d = e.get("dest")
        if e["status"] == "local" and d and d.suffix.lower() == ".md":
            text = d.read_text(encoding="utf-8", errors="ignore")
            for u in DRIVE_RE.findall(text):
                u = u.rstrip(".,;")
                if u not in seen:
                    seen.add(u)
                    drive_extra.append({"url": u, "from": e["title"]})

    # ---------- README.md ----------
    n_local = sum(1 for e in entries if e["status"] == "local")
    n_file = sum(1 for e in entries if e["file_url"])
    n_link = sum(1 for e in entries if not e["file_url"])
    out = []
    out.append("# RoboCup Soccer: библиотека статей, TDP, правил и ссылок\n")
    out.append("Главный индекс. Если файл скачан, ссылка ведёт на копию в репозитории, "
               "если нет — на оригинал в интернете.\n")
    out.append(f"- Файлов в репозитории: **{n_local}** из {n_file} с прямой ссылкой на файл")
    out.append(f"- Только ссылок (блоги, репозитории, платные статьи, страницы): **{n_link}**")
    out.append(f"- Не скачано автоматически: **{len(manual)}** + Google Drive из анкет команд: **{len(drive_extra)}** "
               f"→ см. [MANUAL_DOWNLOAD.md](MANUAL_DOWNLOAD.md)\n")
    out.append("Обновить индекс после ручного скачивания: `python3 build.py --no-download`\n")
    out.append("Оглавление:\n")
    for f, t in FOLDER_TITLES.items():
        out.append(f"- [{t}](#{f.replace('_', '-')})")
    out.append("")

    by_folder = OrderedDict((f, []) for f in FOLDER_TITLES)
    for e in entries:
        by_folder.setdefault(e["folder"], []).append(e)

    for f, items in by_folder.items():
        if not items:
            continue
        out.append(f"## {f}\n")
        out.append(f"**{FOLDER_TITLES.get(f, f)}**\n")
        out.append("| Название | Теги | Файл | Источник |")
        out.append("|---|---|---|---|")
        for e in items:
            title = e["title"].replace("|", "/")
            page = e["page"] or e["file_url"]
            src = f"[источник]({page})" if page else "—"
            if e["status"] == "local":
                fl = f"[📄 {e['filename']}]({rel_link(e['dest'])})"
            elif e["file_url"]:
                fl = f"⬇ нет копии, [оригинал]({e['file_url']})"
            else:
                fl = "— (только ссылка)"
            out.append(f"| {title} | {e['tags']} | {fl} | {src} |")
        out.append("")

    if MANUAL_DIR.exists():
        files = sorted(p for p in MANUAL_DIR.rglob("*") if p.is_file() and p.name != ".gitkeep")
        if files:
            out.append("## _manual_drive\n")
            out.append("**Файлы, скачанные вручную (Google Drive и др.)**\n")
            for p in files:
                out.append(f"- [📄 {p.name}]({rel_link(p)})")
            out.append("")

    (ROOT / "README.md").write_text("\n".join(out) + "\n", encoding="utf-8")

    # ---------- MANUAL_DOWNLOAD.md ----------
    m = []
    m.append("# Скачать вручную\n")
    m.append("Открывайте ссылки по порядку, скачивайте и сохраняйте файл в указанную папку под указанным именем. "
             "Потом выполните `python3 build.py --no-download`, и ссылки в README станут локальными. "
             "Для Google Drive, где имя файла заранее неизвестно, используйте папку `_manual_drive/`.\n")
    n = 0
    if manual:
        m.append("## A. Файлы, которые не скачались автоматически\n")
        for x in manual:
            n += 1
            m.append(f"{n}. [ ] **{x['title']}**  ")
            m.append(f"   Ссылка: {x['url']}  ")
            m.append(f"   Сохранить как: `{x['folder']}/{x['filename']}`  ")
            m.append(f"   Причина: {x['reason']}\n")
    if drive_extra:
        m.append("## B. Google Drive (ссылки из анкет команд)\n")
        for x in drive_extra:
            n += 1
            m.append(f"{n}. [ ] {x['url']}  ")
            m.append(f"   Из анкеты: {x['from']}  ")
            m.append("   Сохранить в: `_manual_drive/`\n")
    if n == 0:
        m.append("Всё скачалось автоматически. Ничего делать не нужно.\n")
    (ROOT / "MANUAL_DOWNLOAD.md").write_text("\n".join(m) + "\n", encoding="utf-8")

    MANUAL_DIR.mkdir(exist_ok=True)
    (MANUAL_DIR / ".gitkeep").touch()

    print(f"\nГотово: локально {n_local}/{n_file}, вручную {n}. Смотрите README.md и MANUAL_DOWNLOAD.md")


if __name__ == "__main__":
    main()
