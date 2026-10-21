"""Pydantic v2 models that validate resume.json, with readable error messages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any, ClassVar, Generic, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

from layout import FONTS, TEMPLATES

# Non-empty text (surrounding whitespace is trimmed).
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
# Text that may be left out or empty.
OptText = Annotated[str, StringConstraints(strip_whitespace=True)]


class Strict(BaseModel):
    """Base for every model: unknown keys are errors, so typos get caught."""

    model_config = ConfigDict(extra="forbid")


class Entry(Strict):
    # The field that names the entry. The ATS check looks for it in the PDF, so it can't be hidden.
    NAME_FIELD: ClassVar[str] = ""

    hidden: bool = False
    hide: list[str] = Field(default_factory=list)  # fields to leave out of the PDF, data kept
    hide_bullets: list[int] = Field(default_factory=list)  # 1-based, same numbering as error messages

    @model_validator(mode="after")
    def _check_hide(self) -> Entry:
        meta = {"hidden", "hide", "hide_bullets"}
        hideable = [f for f in type(self).model_fields if f not in meta and f != self.NAME_FIELD]
        for name in self.hide:
            if name == self.NAME_FIELD:
                raise ValueError(
                    f"'{name}' names this entry and can't be hidden "
                    '(hide the whole entry with "hidden": true instead)'
                )
            if name not in hideable:
                raise ValueError(f"can't hide '{name}': not a field of this entry (choose from: {', '.join(hideable)})")
        if self.hide_bullets:
            have = len(getattr(self, "bullets", []))
            for n in self.hide_bullets:
                if not 1 <= n <= have:
                    raise ValueError(f"hide_bullets has {n}, but this entry has {have} bullet(s)")
        return self

    def text(self, field: str) -> str:
        """The field's text, or "" when it is hidden (what the template prints)."""
        return "" if field in self.hide else getattr(self, field)

    @property
    def visible_bullets(self) -> list[str]:
        if "bullets" in self.hide:
            return []
        return [b for i, b in enumerate(getattr(self, "bullets", []), 1) if i not in self.hide_bullets]


class Basics(Strict):
    name: Text
    location: Text
    citizenship: OptText = ""
    phone: OptText = ""
    email: Text
    linkedin_url: OptText = ""
    linkedin_label: OptText = ""
    github_url: OptText = ""
    github_label: OptText = ""

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        if "@" not in v or " " in v:
            raise ValueError(f"'{v}' does not look like an email address")
        return v

    @field_validator("linkedin_url", "github_url")
    @classmethod
    def _url(cls, v: str) -> str:
        if v and not v.startswith(("http://", "https://")):
            raise ValueError(f"'{v}' must start with http:// or https://")
        return v

    @model_validator(mode="after")
    def _url_needs_label(self) -> Basics:
        for site in ("linkedin", "github"):
            url, label = getattr(self, f"{site}_url"), getattr(self, f"{site}_label")
            if bool(url) != bool(label):
                raise ValueError(
                    f"{site}_url and {site}_label must be filled in together "
                    "(or both left empty to leave it out of the header)"
                )
        return self


class Education(Entry):
    NAME_FIELD: ClassVar[str] = "school"

    school: Text
    location: Text
    degree: Text
    gpa: OptText = ""
    date: Text
    status: OptText = ""  # e.g. "Status - Graduated"; shown instead of `date` by templates that use it
    bullets: list[Text] = Field(default_factory=list)


class Experience(Entry):
    NAME_FIELD: ClassVar[str] = "company"

    company: Text
    location: Text
    title: Text
    dates: Text
    bullets: list[Text] = Field(default_factory=list)


class Project(Entry):
    NAME_FIELD: ClassVar[str] = "name"

    name: Text
    tech: OptText = ""
    date: Text
    bullets: list[Text] = Field(default_factory=list)


class Margins(Strict):
    """Page margins in inches. 0.5 on every side is what the template has always used."""

    top: float = Field(0.5, ge=0.25, le=1.5)
    bottom: float = Field(0.5, ge=0.25, le=1.5)
    left: float = Field(0.5, ge=0.25, le=1.5)
    right: float = Field(0.5, ge=0.25, le=1.5)


class Style(Strict):
    """How the resume looks. Every default reproduces the original hard-coded layout."""

    template: str = "default"
    font: str = "default"
    font_size: float = Field(11.0, ge=8, le=14)  # pt
    margins: Margins = Field(default_factory=Margins)
    # Extra space in pt, added on top of the template's own (negative) tightening.
    section_gap: float = Field(0.0, ge=-3, le=6)
    entry_gap: float = Field(0.0, ge=-3, le=6)
    bullet_gap: float = Field(0.0, ge=-3, le=6)
    fit_to_page: bool = True

    @field_validator("template")
    @classmethod
    def _template(cls, v: str) -> str:
        if v not in TEMPLATES:
            raise ValueError(f"unknown template '{v}'; choose one of: {', '.join(TEMPLATES)}")
        return v

    @field_validator("font")
    @classmethod
    def _font(cls, v: str) -> str:
        if v not in FONTS:
            raise ValueError(f"unknown font '{v}'; choose one of: {', '.join(FONTS)}")
        return v


class Leadership(Entry):
    NAME_FIELD: ClassVar[str] = "organization"

    organization: Text
    location: OptText = ""
    role: Text
    dates: Text
    bullets: list[Text] = Field(default_factory=list)


class Skill(Entry):
    NAME_FIELD: ClassVar[str] = "label"

    label: Text
    items: Text


E = TypeVar("E", bound=Entry)


class Section(Strict, Generic[E]):
    """A section is either a bare list of entries or {"hidden": true, "entries": [...]}."""

    hidden: bool = False
    entries: list[E] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _bare_list(cls, v: Any) -> Any:
        return {"entries": v} if isinstance(v, list) else v

    @property
    def visible(self) -> list[E]:
        """Entries that make it into the PDF ([] when the whole section is hidden)."""
        return [] if self.hidden else [e for e in self.entries if not e.hidden]


def _empty(model: type[Entry]) -> Any:
    return lambda: Section[model](entries=[])  # type: ignore[valid-type]


class Resume(Strict):
    basics: Basics
    education: Section[Education] = Field(default_factory=_empty(Education))
    experience: Section[Experience] = Field(default_factory=_empty(Experience))
    projects: Section[Project] = Field(default_factory=_empty(Project))
    skills: Section[Skill] = Field(default_factory=_empty(Skill))
    leadership: Section[Leadership] = Field(default_factory=_empty(Leadership))
    style: Style = Field(default_factory=Style)


class ResumeError(Exception):
    """Raised with a ready-to-print message when resume.json is invalid."""


_NAME_KEYS = ("school", "company", "name", "organization", "label")


def _where(loc: tuple[int | str, ...], raw: Any) -> str:
    """Turn a pydantic error location into e.g. 'experience > entry #1 ("Acme") > bullet #3 > (field)'."""
    parts: list[str] = []
    node = raw
    prev: int | str | None = None
    for key in loc:
        if isinstance(key, str):
            if key == "entries" and isinstance(node, list):
                prev = key
                continue  # section written as a bare list
            try:
                node = node[key]
            except (KeyError, TypeError, IndexError):
                node = None
            if key != "entries":
                parts.append(key)
        else:
            try:
                node = node[key]
            except (KeyError, TypeError, IndexError):
                node = None
            if prev == "bullets":
                parts[-1] = f"bullet #{key + 1}"
            else:
                label = f"entry #{key + 1}"
                if isinstance(node, dict):
                    name = next((node[k] for k in _NAME_KEYS if isinstance(node.get(k), str)), None)
                    if name:
                        label += f' ("{name}")'
                parts.append(label)
        prev = key
    return " > ".join(parts) or "(top level)"


def _message(err: dict[str, Any]) -> str:
    kind = err["type"]
    if kind == "missing":
        return "required field is missing"
    if kind == "extra_forbidden":
        return "unknown field (check the spelling)"
    if kind == "string_too_short":
        return "must not be empty"
    if kind in ("string_type", "bool_type", "list_type", "model_attributes_type", "dict_type"):
        return f"wrong type: {err['msg'].lower()} (got {type(err.get('input')).__name__})"
    return err["msg"].removeprefix("Value error, ")


def format_errors(exc: ValidationError, raw: Any) -> str:
    lines = []
    for err in exc.errors():
        lines.append(f"  * {_where(tuple(err['loc']), raw)}: {_message(err)}")
    n = len(lines)
    return f"resume.json has {n} problem{'s' if n != 1 else ''}:\n" + "\n".join(lines)


def load_resume(path: Path) -> Resume:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ResumeError(f"{path} not found") from None
    except json.JSONDecodeError as e:
        raise ResumeError(
            f"{path.name} is not valid JSON: {e.msg} at line {e.lineno}, column {e.colno}\n"
            "  (common causes: a missing comma, a trailing comma, or an unescaped \" inside a string)"
        ) from None
    try:
        return Resume.model_validate(raw)
    except ValidationError as e:
        raise ResumeError(format_errors(e, raw)) from None
