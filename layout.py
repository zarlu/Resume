"""Turn a validated Style into the LaTeX fragments the template drops in.

Everything here is duck-typed on the Style model (no import from models.py, which imports
FONTS from this module). Every fragment is empty or identical to the original hard-coded
LaTeX when the style is at its defaults, so an untouched resume renders exactly as before.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_FONT_SIZE = 11.0  # the \documentclass option; the fontsize package is only loaded when it differs
DEFAULT_MARGIN = 0.5  # inches, what the original \addtolength block produced


@dataclass(frozen=True)
class Font:
    label: str
    portable: bool  # bundled with Tectonic (builds anywhere) vs. installed on this computer
    tex: str  # LaTeX that selects it; "" keeps the template's default (Latin Modern)


@dataclass(frozen=True)
class TemplateInfo:
    label: str
    filename: str  # in templates/, resolved by build.render()


TEMPLATES: dict[str, TemplateInfo] = {
    "default": TemplateInfo("Jake's Resume", "resume.tex.j2"),
    "icons": TemplateInfo("Jake's Resume, icon header", "resume-icons.tex.j2"),
    "simple": TemplateInfo("Plain bullet list", "resume-simple.tex.j2"),
}


def _bundled(base: str) -> str:
    return (
        rf"\setmainfont[Extension=.otf,Ligatures=TeX,UprightFont=*-regular,BoldFont=*-bold,"
        rf"ItalicFont=*-italic,BoldItalicFont=*-bolditalic]{{{base}}}"
    )


def _system(name: str) -> str:
    return rf"\setmainfont[Ligatures=TeX]{{{name}}}"


FONTS: dict[str, Font] = {
    "default": Font("Latin Modern (default)", True, ""),
    "termes": Font("TeX Gyre Termes (Times-like)", True, _bundled("texgyretermes")),
    "pagella": Font("TeX Gyre Pagella (Palatino-like)", True, _bundled("texgyrepagella")),
    "heros": Font("TeX Gyre Heros (Helvetica-like)", True, _bundled("texgyreheros")),
    "times-new-roman": Font("Times New Roman", False, _system("Times New Roman")),
    "georgia": Font("Georgia", False, _system("Georgia")),
    "charter": Font("Charter", False, _system("Charter")),
    "helvetica": Font("Helvetica", False, _system("Helvetica")),
    "arial": Font("Arial", False, _system("Arial")),
    # fontspec can't guess Avenir's face names, so without these bold silently renders as regular
    "avenir": Font(
        "Avenir",
        False,
        r"\setmainfont[Ligatures=TeX,BoldFont={Avenir Heavy},ItalicFont={Avenir Oblique},"
        r"BoldItalicFont={Avenir Heavy Oblique}]{Avenir}",
    ),
}


def _num(x: float) -> str:
    """0.5 -> '0.5', 1.0 -> '1', -4.0 -> '-4' (no float noise in the .tex)."""
    return f"{round(x, 3):.3f}".rstrip("0").rstrip(".") or "0"


def _inches(x: float) -> str:
    return f"{_num(x)}in"


def _pt(x: float) -> str:
    return f"{_num(x)}pt"


# The most compact style fit-to-one-page will go to. A value the user already set tighter is kept.
FIT_FLOOR_FONT = 10.0  # pt
FIT_FLOOR_MARGIN = 0.4  # in
FIT_FLOOR_GAP = -2.0  # pt
_DEFAULT_FONT_ACTUAL = 10.95  # what \documentclass[11pt] really sets \normalsize to


def squeezed(style, t: float):
    """The style pulled toward the compact floor by t (0 = as written, 1 = the floor).

    One parameter moves font size, margins and spacing together, so "does it fit" is a single
    monotone search rather than a grid over three levers.
    """
    if t <= 0:
        return style
    font = _DEFAULT_FONT_ACTUAL if style.font_size == DEFAULT_FONT_SIZE else style.font_size

    def toward(value: float, floor: float) -> float:
        return value + t * (min(value, floor) - value)

    m = style.margins
    return style.model_copy(
        update={
            "font_size": toward(font, FIT_FLOOR_FONT),
            "margins": m.model_copy(
                update={side: toward(getattr(m, side), FIT_FLOOR_MARGIN) for side in ("top", "bottom", "left", "right")}
            ),
            "section_gap": toward(style.section_gap, FIT_FLOOR_GAP),
            "entry_gap": toward(style.entry_gap, FIT_FLOOR_GAP),
            "bullet_gap": toward(style.bullet_gap, FIT_FLOOR_GAP),
        }
    )


def describe(style) -> str:
    """'font 10.6pt, margins 0.46in, gaps -0.8pt', collapsing values that are all equal."""
    m = style.margins
    sides = [m.top, m.bottom, m.left, m.right]
    margins = f"{sides[0]:.2f}in" if len(set(sides)) == 1 else "/".join(f"{s:.2f}" for s in sides) + "in (top/bottom/left/right)"
    gaps = [style.section_gap, style.entry_gap, style.bullet_gap]
    g = f"{gaps[0]:.1f}pt" if len(set(gaps)) == 1 else "/".join(f"{x:.1f}" for x in gaps) + "pt (section/entry/bullet)"
    return f"font {style.font_size:.1f}pt, margins {margins}, gaps {g}"


@dataclass(frozen=True)
class Layout:
    preamble: str  # font size, font, margins: dropped in where the margin block used to be
    section_before: str  # the \vspace inside the section-title format (was a literal -4pt)
    entry_extra: str  # extra space before each entry ("" at the default)
    bullet_extra: str  # extra space after each bullet ("" at the default)


def build_layout(style) -> Layout:
    parts: list[str] = []

    if style.font_size != DEFAULT_FONT_SIZE:
        parts.append(rf"\usepackage[fontsize={_pt(style.font_size)}]{{fontsize}}")

    font = FONTS[style.font]
    if font.tex:
        parts.append(r"\usepackage{fontspec}")
        parts.append(font.tex)

    m = style.margins
    # fullpage leaves 1in on every side; the original block took 0.5in back from each.
    left, right = 1 - m.left, 1 - m.right
    top, bottom = 1 - m.top, 1 - m.bottom
    parts += [
        r"% Adjust margins",
        rf"\addtolength{{\oddsidemargin}}{{{_inches(-left)}}}",
        rf"\addtolength{{\evensidemargin}}{{{_inches(-left)}}}",
        rf"\addtolength{{\textwidth}}{{{_inches(left + right)}}}",
        rf"\addtolength{{\topmargin}}{{{_inches(-top)}}}",
        rf"\addtolength{{\textheight}}{{{_inches(top + bottom)}}}",
    ]

    return Layout(
        preamble="\n".join(parts),
        section_before=_pt(-4 + style.section_gap),
        entry_extra=rf"\vspace{{{_pt(style.entry_gap)}}}" if style.entry_gap else "",
        bullet_extra=rf"\vspace{{{_pt(style.bullet_gap)}}}" if style.bullet_gap else "",
    )
