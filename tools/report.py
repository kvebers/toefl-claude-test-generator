"""Render results/<attempt>/report.html and report.pdf.

PDF engines tried in order: Playwright (if installed) -> headless Chrome/Edge/Chromium (CHROME_BIN or auto-detect).
If neither is available only the HTML report is written.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from common import iter_tasks, load_json

TEMPLATES = Path(__file__).resolve().parent / "templates"
BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]


def env() -> Environment:
    e = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]))
    e.filters["label"] = lambda s: str(s).replace("_", " ").capitalize()
    return e


def opt(d: Path, name: str, default=None):
    p = d / name
    return load_json(p) if p.exists() else default


def html_to_pdf(html: Path, pdf: Path) -> str | None:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            page = b.new_page()
            page.goto(html.as_uri())
            page.pdf(path=str(pdf), format="A4", print_background=True,
                     margin={"top": "14mm", "bottom": "14mm", "left": "12mm", "right": "12mm"})
            b.close()
        return "playwright"
    except Exception:
        pass
    candidates = [os.environ.get("CHROME_BIN")] + BROWSERS + [shutil.which(n) for n in
                  ("google-chrome", "chromium", "chromium-browser", "msedge", "chrome")]
    for exe in filter(None, candidates):
        if not Path(exe).exists():
            continue
        r = subprocess.run([exe, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                            f"--print-to-pdf={pdf}", html.as_uri()], capture_output=True, timeout=120)
        if pdf.exists() and pdf.stat().st_size > 0:
            return Path(exe).name
    return None


def context(d: Path) -> dict:
    test, attempt = load_json(d / "test.json"), load_json(d / "attempt.json")
    objective, score = opt(d, "objective.json", {"items": [], "repeats": []}), opt(d, "score.json", {})
    grading = opt(d, "grading.json")
    responses = opt(d, "responses.json", {"tasks": {}})
    transcripts = opt(d, "transcripts.json", {})
    routes = attempt.get("routes", {})
    tasks = {sid: [] for sid in [s["id"] for s in test["sections"]]}
    for sid, mkey, task in iter_tasks(test, routes):
        tasks[sid].append({"module": mkey, **task})
    return {
        "test": test, "attempt": attempt, "objective": objective, "score": score, "grading": grading or {},
        "g_tasks": (grading or {}).get("tasks", {}), "responses": responses.get("tasks", {}),
        "meta": responses.get("meta", {}), "transcripts": transcripts, "tasks": tasks,
        "items_by_section": {sid: [i for i in objective["items"] if i["section"] == sid] for sid in tasks},
    }


def render(d: Path) -> Path:
    html = d / "report.html"
    html.write_text(env().get_template("report.html.j2").render(**context(d)), encoding="utf-8")
    pdf = d / "report.pdf"
    pdf.unlink(missing_ok=True)
    engine = html_to_pdf(html, pdf)
    if not engine:
        print("No PDF engine found (install Chrome/Edge or `pip install playwright && playwright install chromium`); HTML only.")
        return html
    return pdf


if __name__ == "__main__":
    print(render(Path(sys.argv[1])))
