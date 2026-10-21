"""Local web UI: adjust style and visibility with a live PDF preview.   uv run build.py --serve

The browser holds the *working state* (style + what is hidden). Every preview builds that state
in memory into build/preview/ and never touches resume.json or dist/. Only Save (style and
hide flags, merged into a fresh read of resume.json) and Export (dist/) write anything.
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import shutil
import tempfile
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

import build
from layout import FIT_FLOOR_FONT, FIT_FLOOR_GAP, FIT_FLOOR_MARGIN, FONTS, TEMPLATES
from models import Margins, Resume, Style, format_errors

WEB_DIR = Path(__file__).resolve().parent / "web"
SECTION_KEYS = [attr for _, attr, _, _ in build.SECTIONS]
HEADINGS = {attr: heading for heading, attr, _, _ in build.SECTIONS}
KEEP_PREVIEWS = 3

app = FastAPI(title="Resume style UI", docs_url=None, redoc_url=None, openapi_url=None)
_lock = asyncio.Lock()  # one compile at a time; they all write into build/preview/
_latest: dict[str, int] = {}  # per page session: id of its newest preview request
_version = 0
MAX_SESSIONS = 20


# --------------------------------------------------------------------------- request model


class EntryView(BaseModel):
    hidden: bool = False
    hide: list[str] = Field(default_factory=list)
    hide_bullets: list[int] = Field(default_factory=list)


class SectionView(BaseModel):
    hidden: bool = False
    entries: list[EntryView] = Field(default_factory=list)


class ViewState(BaseModel):
    style: dict[str, Any]
    sections: dict[str, SectionView] = Field(default_factory=dict)
    session: str = ""  # one per page load: request ids only supersede each other within a session
    id: int = 0
    fit: bool = False  # preview: also run the fit-to-one-page search if it overflows
    final: bool = False  # export: fail on remaining [placeholders]


# --------------------------------------------------------------------------- resume.json


def read_raw() -> dict:
    path = build.JSON_PATH
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise HTTPException(422, f"{path} not found") from None
    except json.JSONDecodeError as e:
        raise HTTPException(422, f"{path.name} is not valid JSON: {e.msg} at line {e.lineno}, column {e.colno}") from None


def to_resume(raw: dict) -> Resume:
    try:
        return Resume.model_validate(raw)
    except ValidationError as e:
        raise HTTPException(422, format_errors(e, raw)) from None


def entries_of(raw: dict, key: str) -> list:
    section = raw.get(key, [])
    return section if isinstance(section, list) else section.get("entries", [])


def _put(entry: dict, key: str, value: Any) -> None:
    """Set key, or drop it when the value is the default (keeps resume.json free of noise)."""
    if value:
        entry[key] = value
    else:
        entry.pop(key, None)


def apply_view(raw: dict, state: ViewState) -> dict:
    """resume.json's content with the UI's style and hide flags laid over it. Nothing else changes."""
    out = copy.deepcopy(raw)
    out["style"] = state.style
    for key in SECTION_KEYS:
        view = state.sections.get(key)
        if view is None or key not in out:
            continue
        entries = entries_of(out, key)
        if len(view.entries) != len(entries):
            raise HTTPException(409, "resume.json changed on disk since this page loaded. Reload the page.")
        for entry, v in zip(entries, view.entries):
            _put(entry, "hidden", v.hidden)
            _put(entry, "hide", v.hide)
            _put(entry, "hide_bullets", sorted(set(v.hide_bullets)))
        out[key] = {"hidden": True, "entries": entries} if view.hidden else entries
    return out


def _round(x: Any) -> Any:
    if isinstance(x, float):
        return round(x, 3)
    if isinstance(x, dict):
        return {k: _round(v) for k, v in x.items()}
    return x


def write_json_atomic(path: Path, data: dict) -> None:
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".resume-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


# --------------------------------------------------------------------------- outline for the UI


def _bounds(model: type, name: str) -> dict:
    out: dict[str, float] = {}
    for m in model.model_fields[name].metadata:
        for k in ("ge", "le"):
            if hasattr(m, k):
                out["min" if k == "ge" else "max"] = getattr(m, k)
    return out


def outline(resume: Resume) -> list[dict]:
    sections = []
    for heading, attr, name_field, _ in build.SECTIONS:
        section = getattr(resume, attr)
        entries = []
        for e in section.entries:
            fields = [
                {"name": name, "value": f"{len(val)} bullet(s)" if isinstance(val, list) else str(val)}
                for name, val in e.model_dump(exclude={"hidden", "hide", "hide_bullets", name_field}).items()
                if not isinstance(val, list) or name == "bullets"
            ]
            entries.append({
                "name": getattr(e, name_field),
                "hidden": e.hidden,
                "hide": e.hide,
                "hide_bullets": e.hide_bullets,
                "fields": fields,
                "bullets": list(getattr(e, "bullets", [])),
            })
        sections.append({"key": attr, "heading": heading, "hidden": section.hidden, "entries": entries})
    return sections


# --------------------------------------------------------------------------- routes


@app.middleware("http")
async def guard(request: Request, call_next):
    """This server can write files: only answer the local machine, and only to our own page.

    A custom header can't be sent cross-origin without a CORS preflight (which we never
    approve), so a random website can't POST to localhost:8000 on the user's behalf.
    """
    host = request.headers.get("host", "").rsplit(":", 1)[0]
    if host not in ("127.0.0.1", "localhost"):
        return Response("forbidden", status_code=403)
    if request.method == "POST" and request.headers.get("x-resume-ui") != "1":
        return Response("forbidden", status_code=403)
    return await call_next(request)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/api/state")
def get_state() -> dict:
    resume = to_resume(read_raw())
    return {
        "name": resume.basics.name,
        "path": build.JSON_PATH.name,
        "style": _round(resume.style.model_dump()),
        "defaults": Style().model_dump(),
        "fonts": [{"key": k, "label": f.label, "portable": f.portable} for k, f in FONTS.items()],
        "templates": [{"key": k, "label": t.label} for k, t in TEMPLATES.items()],
        "limits": {
            "font_size": _bounds(Style, "font_size"),
            "margin": _bounds(Margins, "top"),
            "gap": _bounds(Style, "section_gap"),
        },
        "fit_floor": {"font_size": FIT_FLOOR_FONT, "margin": FIT_FLOOR_MARGIN, "gap": FIT_FLOOR_GAP},
        "sections": outline(resume),
    }


@app.post("/api/preview")
async def preview(state: ViewState) -> dict:
    global _version
    _latest[state.session] = max(_latest.get(state.session, 0), state.id)
    for stale in list(_latest)[:-MAX_SESSIONS]:  # forget old page loads
        del _latest[stale]

    def superseded() -> bool:
        return state.id < _latest.get(state.session, 0)

    async with _lock:
        if superseded():  # a newer request from the same page arrived while this one waited
            return {"id": state.id, "cancelled": True}
        resume = to_resume(apply_view(read_raw(), state))
        started = time.perf_counter()
        try:
            res = await asyncio.to_thread(
                build.run_build, resume, False, state.fit, build.PREVIEW_DIR, superseded
            )
        except build.BuildCancelled:
            return {"id": state.id, "cancelled": True}
        out: dict[str, Any] = {
            "id": state.id,
            "cancelled": False,
            "ms": round((time.perf_counter() - started) * 1000),
            "result": res.as_dict(),
            "pdf": None,
        }
        if not res.errors and res.pdf:
            _version += 1
            shutil.copyfile(res.pdf, build.PREVIEW_DIR / f"preview-{_version}.pdf")
            for old in build.PREVIEW_DIR.glob("preview-*.pdf"):
                if int(old.stem.split("-")[1]) <= _version - KEEP_PREVIEWS:
                    old.unlink(missing_ok=True)
            out["pdf"] = f"/api/preview/{_version}.pdf"
        return out


@app.get("/api/preview/{version}.pdf")
def preview_pdf(version: int) -> FileResponse:
    path = build.PREVIEW_DIR / f"preview-{version}.pdf"
    if not path.exists():
        raise HTTPException(404, "preview expired")
    return FileResponse(path, media_type="application/pdf", headers={"Cache-Control": "no-store"})


@app.post("/api/save")
async def save(state: ViewState) -> dict:
    async with _lock:
        try:
            state.style = _round(Style.model_validate(state.style).model_dump())
        except ValidationError as e:
            raise HTTPException(422, "; ".join(f"style.{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())) from None
        merged = apply_view(read_raw(), state)  # fresh read: edits made in an editor meanwhile survive
        to_resume(merged)  # never write something the build would reject
        await asyncio.to_thread(write_json_atomic, build.JSON_PATH, merged)
        return {"saved": True, "path": build.JSON_PATH.name}


@app.post("/api/export")
async def export(state: ViewState) -> dict:
    async with _lock:
        resume = to_resume(apply_view(read_raw(), state))
        res = await asyncio.to_thread(build.run_build, resume, state.final, True, build.BUILD_DIR)
        exported = bool(res.ok and res.pdf)
        if exported:
            build.OUTPUT_PDF.parent.mkdir(exist_ok=True)
            shutil.copyfile(res.pdf, build.OUTPUT_PDF)
        return {
            "exported": exported,
            "path": str(build.OUTPUT_PDF.relative_to(build.ROOT)) if exported else None,
            "result": res.as_dict(),
        }


@app.get("/api/download")
def download() -> FileResponse:
    """The last exported PDF, as a browser download."""
    if not build.OUTPUT_PDF.exists():
        raise HTTPException(404, "nothing exported yet")
    return FileResponse(
        build.OUTPUT_PDF,
        media_type="application/pdf",
        filename=build.OUTPUT_PDF.name,
        headers={"Cache-Control": "no-store"},
    )


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


def serve(port: int = 8000) -> None:
    build.PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    url = f"http://127.0.0.1:{port}/"
    print(f"Resume UI running at {url}  (Ctrl+C to stop)")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
