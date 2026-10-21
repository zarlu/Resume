"""Build the resume: resume.json + templates/resume.tex.j2 -> build/resume.tex -> dist/*.pdf

    uv run build.py            build once (shrinks to fit one page if it overflows)
    uv run build.py --final    fail if any [placeholder] remains; render placeholders black
    uv run build.py --watch    rebuild whenever resume.json or the template changes
    uv run build.py --no-fit   report overflow instead of shrinking to one page
    uv run build.py --serve    open the live styling UI in the browser
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from pypdf import PdfReader

from layout import TEMPLATES, build_layout, describe, squeezed
from models import Resume, ResumeError, Style, load_resume

ROOT = Path(__file__).resolve().parent
JSON_PATH = ROOT / "resume.json"
EXAMPLE_PATH = ROOT / "resume.example.json"
TEMPLATE_DIR = ROOT / "templates"
BUILD_DIR = ROOT / "build"
PREVIEW_DIR = BUILD_DIR / "preview"
DIST_DIR = ROOT / "dist"
OUTPUT_PDF = DIST_DIR / "Resume.pdf"

FIT_STEPS = 6  # binary-search steps: resolves the squeeze to 1/64, about 2 seconds of compiles

# (heading, Resume attribute, field holding the entry's name, check entry names for ATS?)
SECTIONS = [
    ("Education", "education", "school", True),
    ("Experience", "experience", "company", True),
    ("Projects", "projects", "name", True),
    ("Technical Skills", "skills", "label", False),
    ("Leadership / Extracurricular", "leadership", "organization", True),
]

# Templates that print a different literal heading than SECTIONS' canonical name
# (checked here, not derived from the .tex.j2, so the page/ATS checks know what to look for).
TEMPLATE_HEADINGS: dict[str, dict[str, str]] = {
    "simple": {"education": "Education & Certificates", "experience": "Work History"},
}

_COLOR = sys.stdout.isatty()
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


PASS, FAIL = c("PASS", "32"), c("FAIL", "31;1")


# --------------------------------------------------------------------------- text -> LaTeX

_ESCAPES = {
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "^": r"\^{}",
    "\\": r"\textbackslash{}",
}
_BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
_ITALIC = re.compile(r"\*(?=\S)(.+?)(?<=\S)\*")
_PLACEHOLDER = re.compile(r"\[[^\[\]]*\]")


def escape(text: str) -> str:
    """Escape LaTeX special characters in one pass (so nothing is escaped twice).

    "~" becomes a math tilde ($\\sim$, "approximately") when it precedes a digit,
    matching how the resume was originally typeset, and \\textasciitilde{} otherwise.
    "--" is left alone: LaTeX renders it as an en dash.
    """
    out = []
    for i, ch in enumerate(text):
        if ch == "~":
            out.append(r"$\sim$" if text[i + 1 : i + 2].isdigit() else r"\textasciitilde{}")
        else:
            out.append(_ESCAPES.get(ch, ch))
    return "".join(out)


def tex(text: str | None) -> str:
    """Plain text with light markup -> LaTeX. Escapes first, then applies markup."""
    if not text:
        return ""
    s = escape(text)
    s = _BOLD.sub(r"\\textbf{\1}", s)
    s = _ITALIC.sub(r"\\emph{\1}", s)
    return _PLACEHOLDER.sub(lambda m: r"\ph{" + m.group(0) + "}", s)


def url(text: str | None) -> str:
    """Make a URL / mailto target safe inside \\href{...}{...}."""
    return (text or "").replace("\\", "/").replace("%", r"\%").replace("#", r"\#")


def make_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        block_start_string="((*",
        block_end_string="*))",
        variable_start_string="(((",
        variable_end_string=")))",
        comment_start_string="((#",
        comment_end_string="#))",
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        autoescape=False,
        undefined=StrictUndefined,
    )
    env.filters["tex"] = tex
    env.filters["url"] = url
    return env


def render(resume: Resume, final: bool, style: Style | None = None) -> str:
    """The .tex source. `style` overrides resume.style (fit-to-page renders squeezed variants)."""
    style = style or resume.style
    filename = TEMPLATES[style.template].filename
    return make_env().get_template(filename).render(
        layout=build_layout(style),
        basics=resume.basics,
        education=resume.education.visible,
        experience=resume.experience.visible,
        projects=resume.projects.visible,
        skills=resume.skills.visible,
        leadership=resume.leadership.visible,
        final=final,
    )


# --------------------------------------------------------------------------- compile

Message = tuple[str, str | None]  # (text, ANSI colour code or None)


def find_tectonic() -> str | None:
    return shutil.which("tectonic") or (
        str(p) if (p := ROOT / "tools" / "tectonic").exists() else None
    )


def compile_tex(tex_path: Path, outdir: Path) -> list[Message]:
    """Compile tex_path into outdir. Returns the error messages to show, or [] on success."""
    exe = find_tectonic()
    if not exe:
        return [("error: tectonic not found. Install it with `brew install tectonic` "
                 "(macOS) or `winget install TectonicTypesetting.Tectonic` (Windows).", None)]
    proc = subprocess.run(
        [exe, "-X", "compile", "--outdir", str(outdir), str(tex_path)],
        capture_output=True, text=True, cwd=ROOT,
    )
    if proc.returncode != 0:
        tail = "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-25:])
        return [("error: LaTeX compilation failed. Last lines of output:", "31"), (tail, None)]
    return []


# --------------------------------------------------------------------------- checks


def squash(s: str) -> str:
    """Normalise for matching: ligatures, curly quotes, dashes, all whitespace, case."""
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    s = re.sub(r"[\u2010-\u2015\u2212]", "-", s)
    return re.sub(r"\s+", "", s).casefold()


def plain(s: str) -> str:
    """Source text as it should appear in the PDF (markup removed, '--' as a dash)."""
    return re.sub(r"\*+", "", s).replace("--", "-")


def visible_sections(resume: Resume):
    """Yield (heading, entries, name_field, check_names, attr) for sections that reach the PDF."""
    overrides = TEMPLATE_HEADINGS.get(resume.style.template, {})
    for heading, attr, name_field, check in SECTIONS:
        entries = getattr(resume, attr).visible
        if entries:
            yield overrides.get(attr, heading), entries, name_field, check, attr


def is_heading(line: str, heading: str) -> bool:
    return squash(line) == squash(heading)


def check_page_count(pages: list[str], resume: Resume, note: str = "") -> tuple[bool, list[str]]:
    """(ok, the lines to print). `note` is an extra line shown before the generic fix hint."""
    n = len(pages)
    if n == 1:
        return True, [f"  {PASS}  page count: 1"]
    lines = [f"  {FAIL}  page count: {n} (must be exactly 1)"]
    later = [ln for p in pages[1:] for ln in p.splitlines() if ln.strip()]
    headings = [h for h, *_ in visible_sections(resume)]
    on_first = [h for h in headings if any(is_heading(ln, h) for ln in pages[0].splitlines())]
    if later and any(is_heading(later[0], h) for h in headings):
        spill = f"'{later[0].strip()}' (the whole section starts on page 2)"
    elif on_first:
        spill = f"'{on_first[-1]}' (it runs past the bottom of page 1)"
    else:
        spill = "unknown"
    lines.append(f"        Overflow starts in section: {spill}")
    later_sq = squash("\n".join(later))
    spilled = [
        f"{heading}: {plain(getattr(e, field_))}"
        for heading, entries, field_, check, _attr in visible_sections(resume) if check
        for e in entries if squash(plain(getattr(e, field_))) in later_sq
    ]
    if spilled:
        lines.append("        Entries on page 2: " + "; ".join(spilled))
    lines.append(f"        {len(later)} line(s) spill over; first: \"{later[0].strip()[:90]}\"" if later else "")
    if note:
        lines.append(f"        {note}")
    lines.append("        Fix: shorten bullets, or set \"hidden\": true on a bullet-heavy entry/section.")
    return False, lines


@dataclass
class Check:
    status: str  # "pass" | "fail"
    label: str
    text: str
    why: str = ""

    def line(self) -> str:
        if self.status == "pass":
            return f"  {PASS}  {self.label}: {self.text}"
        return f"  {FAIL}  {self.label}: {self.text}  ({self.why})"


def check_ats(pages: list[str], resume: Resume) -> tuple[bool, list[Check]]:
    lines = [ln for p in pages for ln in p.splitlines() if ln.strip()]
    sq_lines = [squash(ln) for ln in lines]
    expected: list[tuple[str, str, str]] = [
        ("name", resume.basics.name, "text"),
        ("email", resume.basics.email, "text"),
    ]
    for heading, entries, field_, check, attr in visible_sections(resume):
        expected.append(("heading", heading, "heading"))
        if check:
            expected += [(field_label(attr), getattr(e, field_), "text") for e in entries]

    ok, cursor = True, 0
    checks: list[Check] = []
    for label, value, kind in expected:
        want = squash(plain(value))

        def hit(i: int) -> bool:
            return sq_lines[i] == want if kind == "heading" else want in sq_lines[i]

        found = next((i for i in range(cursor, len(lines)) if hit(i)), None)
        if found is not None:
            cursor = found
            checks.append(Check("pass", label, plain(value)))
            continue
        ok = False
        anywhere = any(hit(i) for i in range(len(lines)))
        why = "found, but out of reading order" if anywhere else "not found in PDF text"
        checks.append(Check("fail", label, plain(value), why))
    return ok, checks


def field_label(attr: str) -> str:
    return {
        "education": "school",
        "experience": "company",
        "projects": "project",
        "leadership": "organization",
    }.get(attr, "entry")


def find_placeholders(resume: Resume) -> list[tuple[str, str]]:
    """Every [bracketed] item in the visible content, with where it lives."""
    hits: list[tuple[str, str]] = []

    def scan(where: str, text: str) -> None:
        hits.extend((where, m.group(0)) for m in _PLACEHOLDER.finditer(text))

    for key, val in resume.basics.model_dump().items():
        scan(f"Header > {key}", val)
    for heading, entries, name_field, _check, _attr in visible_sections(resume):
        for e in entries:
            name = getattr(e, name_field)
            for key, val in e.model_dump(exclude={"hidden", "hide", "hide_bullets"}).items():
                if key in e.hide:
                    continue
                if isinstance(val, list):
                    for i, b in enumerate(val, 1):
                        if i not in e.hide_bullets:
                            scan(f"{heading} > {name} > bullet #{i}", b)
                else:
                    scan(f"{heading} > {name} > {key}", val)
    return hits


# --------------------------------------------------------------------------- build


@dataclass
class Fit:
    """What fit-to-one-page changed (the build used `style`; resume.json is untouched)."""

    squeeze: float
    style: Style

    def describe(self) -> str:
        return f"Fit to 1 page: squeeze {round(self.squeeze * 100)}% ({describe(self.style)})"


@dataclass
class BuildResult:
    ok: bool = False
    errors: list[Message] = field(default_factory=list)  # set when the build died before any check
    page_count: int = 0
    page_ok: bool = False
    page_lines: list[str] = field(default_factory=list)
    ats_ok: bool = False
    ats: list[Check] = field(default_factory=list)
    placeholders: list[tuple[str, str]] = field(default_factory=list)
    placeholders_ok: bool = False
    fit: Fit | None = None
    pdf: Path | None = None

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "errors": [t for t, _ in self.errors],
            "pages": {"count": self.page_count, "ok": self.page_ok, "lines": [_ANSI.sub("", ln) for ln in self.page_lines]},
            "ats": {"ok": self.ats_ok, "checks": [vars(k) for k in self.ats]},
            "placeholders": [{"where": w, "text": t} for w, t in self.placeholders],
            "fit": None if not self.fit else {
                "squeeze": self.fit.squeeze,
                "description": self.fit.describe(),
                "style": self.fit.style.model_dump(),
            },
        }


def _pages(pdf: Path) -> list[str]:
    return [p.extract_text() or "" for p in PdfReader(pdf).pages]


class BuildCancelled(Exception):
    """Raised between compile steps when the caller no longer wants the result (live UI)."""


class _Compiler:
    """Renders + compiles one resume into an output dir, remembering which style is on disk."""

    def __init__(self, resume: Resume, final: bool, outdir: Path, should_stop: Callable[[], bool] | None = None):
        self.resume, self.final, self.outdir, self.should_stop = resume, final, outdir, should_stop
        self.tex_path = outdir / "resume.tex"
        self.pdf = outdir / "resume.pdf"
        self.last_t: float | None = None
        outdir.mkdir(parents=True, exist_ok=True)

    def at(self, t: float) -> tuple[list[str] | None, list[Message]]:
        """Compile with the style squeezed by t. Returns (page texts, errors)."""
        if self.should_stop and self.should_stop():
            raise BuildCancelled
        squeezed_style = squeezed(self.resume.style, t)
        try:
            self.tex_path.write_text(render(self.resume, self.final, squeezed_style), encoding="utf-8")
        except Exception as e:  # template syntax/undefined-variable errors
            filename = TEMPLATES[squeezed_style.template].filename
            return None, [(f"error: rendering {filename} failed: {e}", "31")]
        if errors := compile_tex(self.tex_path, self.outdir):
            return None, errors
        self.last_t = t
        return _pages(self.pdf), []


def _fit(comp: _Compiler) -> tuple[float | None, list[str], list[Message]]:
    """Smallest squeeze at which the resume is one page (None if even the floor overflows)."""
    floor_pages, errors = comp.at(1.0)
    if errors or floor_pages is None:
        return None, [], errors
    if len(floor_pages) > 1:
        return None, floor_pages, []
    lo, hi, best = 0.0, 1.0, floor_pages
    for _ in range(FIT_STEPS):
        mid = (lo + hi) / 2
        pages, errors = comp.at(mid)
        if errors or pages is None:
            return None, [], errors
        if len(pages) == 1:
            hi, best = mid, pages
        else:
            lo = mid
    if comp.last_t != hi:  # leave the PDF on disk matching the style we report
        best, errors = comp.at(hi)
        if errors or best is None:
            return None, [], errors
    return hi, best, []


def run_build(
    resume: Resume,
    final: bool = False,
    fit: bool = True,
    outdir: Path = BUILD_DIR,
    should_stop: Callable[[], bool] | None = None,
) -> BuildResult:
    """Render, compile and check. Prints nothing and never touches dist/.

    Raises BuildCancelled if `should_stop()` turns true between compile steps.
    """
    res = BuildResult(pdf=outdir / "resume.pdf")
    comp = _Compiler(resume, final, outdir, should_stop)
    pages, errors = comp.at(0.0)
    if errors or pages is None:
        res.errors = errors
        return res

    note = ""
    if len(pages) > 1 and fit and resume.style.fit_to_page:
        t, fitted, errors = _fit(comp)
        if errors:
            res.errors = errors
            return res
        if t is not None:
            pages = fitted
            res.fit = Fit(t, squeezed(resume.style, t))
        else:
            pages = fitted or pages
            floor = squeezed(resume.style, 1.0)
            note = f"Squeezed to the floor ({describe(floor)}) and it still doesn't fit."

    res.page_count = len(pages)
    res.page_ok, res.page_lines = check_page_count(pages, resume, note)
    if res.fit and res.page_ok:
        res.page_lines.append(f"        {res.fit.describe()}")
    res.ats_ok, res.ats = check_ats(pages, resume)
    res.placeholders = find_placeholders(resume)
    res.placeholders_ok = not res.placeholders or not final
    res.ok = res.page_ok and res.ats_ok and res.placeholders_ok
    return res


def print_report(res: BuildResult, final: bool) -> None:
    for text, code in res.errors:
        print(c(text, code) if code else text)
    if res.errors:
        return
    print("Page count:")
    print("\n".join(res.page_lines))
    print("ATS text check (PDF text, reading order):")
    for k in res.ats:
        print(k.line())
    print("Placeholders:")
    if not res.placeholders:
        print(f"  {PASS}  no placeholders remain")
        return
    label = FAIL if final else c("INFO", "33")
    print(f"  {label}  {len(res.placeholders)} placeholder(s) remaining:")
    for where, text in res.placeholders:
        print(f"          {text:<40} {where}")


def ensure_resume() -> None:
    """First run: start your own resume.json (git-ignored) from the sample."""
    if JSON_PATH.exists() or not EXAMPLE_PATH.exists():
        return
    shutil.copyfile(EXAMPLE_PATH, JSON_PATH)
    print(c(f"Created {JSON_PATH.name} from {EXAMPLE_PATH.name}. Edit it with your own details.", "36"))


def build(final: bool = False, fit: bool = True) -> bool:
    ensure_resume()
    print(c(f"\n== Building resume{' (--final)' if final else ''} ==", "1"))
    try:
        resume = load_resume(JSON_PATH)
    except ResumeError as e:
        print(c(str(e), "31"))
        return False

    res = run_build(resume, final, fit, BUILD_DIR)
    print_report(res, final)
    if res.errors:
        return False

    out = OUTPUT_PDF
    if res.ok:
        DIST_DIR.mkdir(exist_ok=True)
        shutil.copyfile(BUILD_DIR / "resume.pdf", out)
        print(c(f"\nOK  {out.relative_to(ROOT)}", "32;1"))
        return True
    print(c(f"\nBUILD FAILED  ({out.relative_to(ROOT)} left unchanged; "
            f"the failed attempt is in build/resume.pdf)", "31;1"))
    return False


def watch(final: bool, fit: bool) -> None:
    from watchfiles import watch as watch_files

    ensure_resume()
    targets = [JSON_PATH, TEMPLATE_DIR]
    build(final, fit)
    print(c("\nWatching resume.json and templates/. Ctrl+C to stop.", "36"))
    try:
        for _ in watch_files(*targets, debounce=300):
            build(final, fit)
            print(c("\nWatching... (Ctrl+C to stop)", "36"))
    except KeyboardInterrupt:
        print("\nStopped.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--final", action="store_true",
                    help="fail if any [placeholder] remains; render placeholders black")
    ap.add_argument("--watch", action="store_true",
                    help="rebuild whenever resume.json or the template changes")
    ap.add_argument("--no-fit", action="store_true",
                    help="report overflow instead of shrinking the layout to one page")
    ap.add_argument("--serve", action="store_true", help="open the live styling UI in the browser")
    ap.add_argument("--port", type=int, default=8000, help="port for --serve (default 8000)")
    args = ap.parse_args()
    if args.serve:
        from server import serve

        ensure_resume()
        serve(args.port)
        return 0
    if args.watch:
        watch(args.final, not args.no_fit)
        return 0
    return 0 if build(args.final, not args.no_fit) else 1


if __name__ == "__main__":
    sys.exit(main())
