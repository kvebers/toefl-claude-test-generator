"""Local exam runner: serves the web UI, hands out answer-free tests, stores responses and recordings,
does adaptive routing server-side, and launches grading on submit.

usage: python server/app.py [--test <id>|latest] [--port 8765] [--open] [--home-edition]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
import webbrowser
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from common import (RESULTS_DIR, ROOT, TESTS_DIR, find_test_dir, latest_test_id, list_tests,  # noqa: E402
                    load_json, load_spec, next_untaken_test_id, sanitize, save_json, score_module)
from validate import validate  # noqa: E402
from bank import run_generation  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
MAX_UPLOAD = 25 * 1024 * 1024
LEVELS = {"", "easy", "medium", "hard", "mixed"}
JOBS: dict[str, dict] = {}                       # generation jobs started from the browser
JOB_QUEUE = ThreadPoolExecutor(max_workers=1)    # one Claude generation at a time


def run_job(job: dict) -> None:
    job.update(state="running", started=time.time())
    try:
        job["tests"] = run_generation(job["prompt"], TESTS_DIR / ".jobs" / f"{job['id']}.log")
        job["state"] = "done" if job["tests"] else "failed"
        if not job["tests"]:
            job["error"] = f"No test was created. See tests/.jobs/{job['id']}.log"
    except Exception as e:  # CLI missing etc.
        job.update(state="failed", error=str(e))
    job["finished"] = time.time()


def safe_join(base: Path, *parts: str) -> Path:
    p = base.joinpath(*parts).resolve()
    if not p.is_relative_to(base.resolve()):
        raise PermissionError(p)
    return p


def attempt_dir(aid: str) -> Path:
    d = safe_join(RESULTS_DIR, aid)
    if not (d / "attempt.json").exists():
        raise FileNotFoundError(aid)
    return d


def run_tool(args: list[str], log: Path | None = None) -> subprocess.Popen:
    out = open(log, "a", encoding="utf-8") if log else subprocess.DEVNULL
    return subprocess.Popen([sys.executable, *args], cwd=ROOT, stdout=out, stderr=subprocess.STDOUT)


class Handler(SimpleHTTPRequestHandler):
    server_version = "toefl-runner"

    def log_message(self, fmt, *args):
        if self.command != "GET" or "/api/" in self.path:
            sys.stderr.write(f"{self.command} {self.path.split('?')[0]} {args[1] if len(args) > 1 else ''}\n")

    # ------------------------------------------------------------ helpers
    def send_json(self, data, status=HTTPStatus.OK):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path: Path, download: str | None = None):
        if not path.is_file():
            return self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", self.guess_type(str(path)))
        self.send_header("Content-Length", str(len(data)))
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{download}"')
        self.end_headers()
        self.wfile.write(data)

    def body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_UPLOAD:
            raise ValueError("upload too large")
        return self.rfile.read(n)

    def route(self, method: str):
        url = urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            handler = getattr(self, f"{method}_{parts[0] if parts else 'index'}", None)
            if parts and parts[0] == "api" and len(parts) > 1:
                handler = getattr(self, f"{method}_api_{parts[1]}", None)
                parts = parts[2:]
            elif parts:
                parts = parts[1:]
            if handler is None:
                return self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return handler(parts, query)
        except FileNotFoundError as e:
            self.send_json({"error": f"not found: {e}"}, HTTPStatus.NOT_FOUND)
        except (PermissionError, ValueError, KeyError, json.JSONDecodeError) as e:
            self.send_json({"error": str(e)}, HTTPStatus.BAD_REQUEST)

    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        # Only pages served by this server may POST (stops other websites from triggering
        # Claude runs or writing results through your browser).
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        if origin and origin not in (f"http://{host}", f"http://127.0.0.1:{self.server.server_port}",
                                     f"http://localhost:{self.server.server_port}"):
            return self.send_json({"error": "cross-origin request refused"}, HTTPStatus.FORBIDDEN)
        self.route("POST")

    # ------------------------------------------------------------ static
    def GET_index(self, parts, q):
        self.send_file(STATIC / "index.html")

    def GET_static(self, parts, q):
        self.send_file(safe_join(STATIC, *parts))

    def GET_media(self, parts, q):            # /media/<test_id>/<file>
        self.send_file(safe_join(find_test_dir(parts[0]) / "audio", *parts[1:]))

    def GET_results(self, parts, q):          # /results/<attempt>/<file>
        self.send_file(safe_join(RESULTS_DIR, *parts))

    # ------------------------------------------------------------ tests
    def GET_api_config(self, parts, q):
        spec = load_spec()
        self.send_json({"default_test": self.server.default_test, "home_edition": self.server.home_edition,
                        "spec": {"sections": spec["sections"], "order": spec["order"],
                                 "home_edition": spec["home_edition"]}})

    def GET_api_tests(self, parts, q):
        if not parts:
            return self.send_json(list_tests())
        d = find_test_dir(parts[0])
        if len(parts) > 1 and parts[1] == "download":   # export a test to share it
            return self.send_file(d / "test.json", download=f"{parts[0]}.json")
        manifest = d / "audio" / "manifest.json"
        self.send_json({"test": sanitize(load_json(d / "test.json")),
                        "audio": load_json(manifest) if manifest.exists() else None})

    def POST_api_tests(self, parts, q):      # /api/tests/import  (load a test file someone shared)
        test = json.loads(self.body())
        errors, warnings = validate(test)
        if errors:
            return self.send_json({"error": "invalid test", "details": errors[:20]}, HTTPStatus.BAD_REQUEST)
        base, n = test["id"], 1
        while (TESTS_DIR / test["id"]).exists() or (ROOT / "library" / test["id"]).exists():
            n += 1
            test["id"] = f"{base}-{n}"
        save_json(TESTS_DIR / test["id"] / "test.json", test)
        run_tool(["tools/tts.py", test["id"]])
        self.send_json({"id": test["id"], "warnings": warnings})

    # ------------------------------------------------------------ generation jobs
    def GET_api_jobs(self, parts, q):
        now = time.time()
        self.send_json([{**{k: v for k, v in j.items() if k != "prompt"},
                         "elapsed": round((j.get("finished") or now) - (j.get("started") or now))}
                        for j in sorted(JOBS.values(), key=lambda j: j["created"], reverse=True)])

    def POST_api_jobs(self, parts, q):
        req = json.loads(self.body() or b"{}")
        spec = load_spec()
        tasks = {t for s in spec["sections"].values() for t in s["tasks"]}
        target, level = req.get("target", "full"), req.get("level", "")
        if target not in {"full", "weakest", *spec["sections"], *tasks} or level not in LEVELS:
            raise ValueError("unknown target or level")
        count = max(1, min(5, int(req.get("count", 1))))
        made = []
        for _ in range(count):
            prompt = f"/toefl-generate full {level}" if target == "full" else f"/toefl-practice {target} {level}"
            job = {"id": uuid.uuid4().hex[:8], "target": target, "level": level or "default", "state": "queued",
                   "created": time.time(), "prompt": prompt.strip(), "tests": []}
            JOBS[job["id"]] = job
            JOB_QUEUE.submit(run_job, job)
            made.append(job["id"])
        self.send_json({"jobs": made})

    # ------------------------------------------------------------ attempts
    def GET_api_attempts(self, parts, q):
        if not parts:
            index = RESULTS_DIR / "index.jsonl"
            rows = [json.loads(l) for l in index.read_text(encoding="utf-8").splitlines() if l.strip()] \
                if index.exists() else []
            return self.send_json(rows[::-1])
        d = attempt_dir(parts[0])
        status = load_json(d / "status.json") if (d / "status.json").exists() else {"stage": "in_progress"}
        if (d / "score.json").exists():
            status["score"] = load_json(d / "score.json")["summary"]
        status["report_pdf"] = (d / "report.pdf").exists()
        status["report_html"] = (d / "report.html").exists()
        self.send_json(status)

    def POST_api_attempts(self, parts, q):
        if not parts:                                   # start a new attempt
            req = json.loads(self.body() or b"{}")
            test_id = req["test_id"]
            src = find_test_dir(test_id)
            aid = f"{datetime.now():%Y%m%d-%H%M%S}_{test_id}"
            d = RESULTS_DIR / aid
            (d / "recordings").mkdir(parents=True)
            test = load_json(src / "test.json")                         # snapshot with answer key
            if req.get("sections"):                                     # single-section attempt
                test["sections"] = [sec for sec in test["sections"] if sec["id"] in req["sections"]]
                if not test["sections"]:
                    raise ValueError("no such section in this test")
                test["mode"] = "practice"
            save_json(d / "test.json", test)
            save_json(d / "attempt.json", {"id": aid, "test_id": test_id, "source": src.parent.name,
                                           "started": datetime.now().isoformat(timespec="seconds"),
                                           "home_edition": bool(req.get("home_edition")), "routes": {},
                                           "sections": [sec["id"] for sec in test["sections"]]})
            return self.send_json({"attempt_id": aid})

        d = attempt_dir(parts[0])
        action = parts[1] if len(parts) > 1 else ""
        if action == "responses":
            if "finished" not in load_json(d / "attempt.json"):    # after submit the answers are frozen for grading
                save_json(d / "responses.json", json.loads(self.body()))
            return self.send_json({"ok": True})
        if action == "recording":                       # raw audio body, ?key=<task>__<item>
            key = q["key"]
            if not key.replace("_", "").replace("-", "").isalnum():
                raise ValueError("bad key")
            ext = "ogg" if "ogg" in (self.headers.get("Content-Type") or "") else "webm"
            (d / "recordings" / f"{key}.{ext}").write_bytes(self.body())
            return self.send_json({"ok": True})
        if action == "route":                           # multistage adaptive routing
            req = json.loads(self.body())
            section, responses = req["section"], req.get("responses", {})
            test = load_json(d / "test.json")
            sec = next(s for s in test["sections"] if s["id"] == section)
            if "m2_easy" not in sec["modules"]:
                return self.send_json({"module": None})
            threshold = load_spec()["sections"][section]["routing_threshold"]
            module = "m2_hard" if score_module(section, "m1", sec["modules"]["m1"], responses) >= threshold \
                else "m2_easy"
            attempt = load_json(d / "attempt.json")
            attempt["routes"][section] = module
            save_json(d / "attempt.json", attempt)
            return self.send_json({"module": module})
        if action == "submit":
            if req := self.body():
                save_json(d / "responses.json", json.loads(req))
            attempt = load_json(d / "attempt.json")
            attempt["finished"] = datetime.now().isoformat(timespec="seconds")
            save_json(d / "attempt.json", attempt)
            save_json(d / "status.json", {"stage": "queued"})
            run_tool(["tools/pipeline.py", "grade", d.name], log=d / "pipeline.log")
            return self.send_json({"ok": True})
        raise ValueError(f"unknown action {action}")


def render_missing_audio(first: str | None) -> None:
    """Library tests are committed without audio. Render the test being opened now, the rest in the background."""
    missing = [t["id"] for t in list_tests() if not t["audio_ready"]]
    if first in missing:
        print(f"Rendering voices for {first} (first time only, about a minute)…", flush=True)
        subprocess.run([sys.executable, "tools/tts.py", first], cwd=ROOT, check=False)
        missing.remove(first)
    if missing:
        threading.Thread(target=lambda: [subprocess.run([sys.executable, "tools/tts.py", t], cwd=ROOT, check=False,
                                                        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
                                         for t in missing], daemon=True).start()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", default=None, help="test id to preselect, 'latest', or 'next' (oldest untaken)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--open", action="store_true")
    ap.add_argument("--home-edition", action="store_true")
    a = ap.parse_args()
    RESULTS_DIR.mkdir(exist_ok=True)
    TESTS_DIR.mkdir(exist_ok=True)
    default = {"latest": latest_test_id, "next": next_untaken_test_id}.get(a.test, lambda: a.test)()
    if default:
        find_test_dir(default)
    render_missing_audio(default)
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    srv.default_test, srv.home_edition = default, a.home_edition
    url = f"http://127.0.0.1:{a.port}/" + (f"?test={default}" if default else "")
    print(f"TOEFL runner on {url}  (Ctrl+C to stop)")
    if a.open:
        threading.Timer(0.6, webbrowser.open, [url]).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
