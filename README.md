# Resume build: the complete guide

Your resume lives in one file, `resume.json`. A build script turns it into a one-page, ATS-safe PDF
(`dist/Resume.pdf`) using a LaTeX template (Jake's Resume) and Tectonic. A local
**web UI** lets you change the look, hide things and watch the PDF update live.

**Contents**

1. [Quick start](#1-quick-start)
2. [How it works](#2-how-it-works)
3. [The web UI](#3-the-web-ui) (the main way to use this)
4. [Editing your content](#4-editing-your-content-resumejson)
5. [Hiding things](#5-hiding-things)
6. [Style reference](#6-style-reference)
7. [Command line reference](#7-command-line-reference)
8. [What the checks mean](#8-what-the-checks-mean)
9. [Troubleshooting](#9-troubleshooting)
10. [Project layout](#10-project-layout)
11. [License and credits](#11-license-and-credits)

---

## 1. Quick start

**Install once:**

```sh
brew install tectonic uv                                # macOS
winget install TectonicTypesetting.Tectonic astral-sh.uv  # Windows
```

On Linux, install [Tectonic](https://tectonic-typesetting.github.io) and [uv](https://docs.astral.sh/uv/) from
their sites. You need Python 3.12 or newer (uv fetches one if missing).

**Get the code:**

```sh
git clone <this repo's URL>
cd <the cloned folder>
```

The first run creates `resume.json` (your own copy, ignored by git) from `resume.example.json`.
Replace its contents with your details, or open the UI and start from the sample.

`uv run` installs the Python packages by itself. The first build downloads a few LaTeX packages and
caches them; if you pick a font or feature you haven't used before, Tectonic may download more the
first time.

**Build the PDF:**

```sh
uv run build.py
```

**Open the live UI:**

```sh
uv run build.py --serve
```

Your browser opens `http://127.0.0.1:8000`. Change something on the left, and the PDF on the right
rebuilds in about half a second. Press **Ctrl+C** in the terminal to stop it.

**Before you send the resume:** fill in every red `[placeholder]`, then run
`uv run build.py --final`. It refuses to build while any placeholder is left.

---

## 2. How it works

```
 resume.json ──►  build.py  ──►  LaTeX  ──►  Tectonic  ──►  PDF  ──►  checks
 (content +       (template +      (build/                              1 page? ATS text?
  style + hide)    style)           resume.tex)                         placeholders left?
                                                                            │
                                            all pass ──► dist/Resume.pdf
```

Everything you can change falls into three layers, all stored in `resume.json`:

| Layer | Answers | Where in `resume.json` | Changed with |
|-------|---------|------------------------|--------------|
| **Content** | What does it say? | `basics`, `education`, `experience`, `projects`, `skills`, `leadership` | your text editor |
| **Style** | How does it look? | the `style` block | the web UI, or by hand |
| **Visibility** | What is shown? | `hidden`, `hide`, `hide_bullets` on entries; `hidden` on sections | the web UI, or by hand |

Two rules to remember:

- **The web UI changes style and visibility, never your wording.** Wording is edited in `resume.json`.
- **Nothing is saved until you press Save style.** The UI works on a temporary copy in memory.
  `dist/` is only written by **Export PDF** (or `uv run build.py`), and only when every check passes.

---

## 3. The web UI

### 3.1 Start and stop

```sh
uv run build.py --serve              # http://127.0.0.1:8000
uv run build.py --serve --port 9000  # another port, if 8000 is taken
```

- The browser opens by itself. If it doesn't, open the printed address.
- **Ctrl+C** in the terminal stops it. Closing the browser tab does not.
- It only listens on your own computer (`127.0.0.1`) and ignores requests that don't come from its
  own page, so a website can't make it change your files.
- Your browser's built-in PDF viewer shows the preview.

### 3.2 The screen

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ● Alex Rivera: style  [1 page][ATS 14/14][35 placeholders][393 ms]       │
│                                     ☐ Final  [Revert] [Save style] [Export PDF]│
├───────────────────────────┬──────────────────────────────────────────────────┤
│ FONT                      │                                                  │
│ [ Latin Modern (default)▾]│                                                  │
│ TEXT SIZE                 │                                                  │
│ Size ──●───── 11pt        │            live PDF preview                      │
│ MARGINS                   │        (the real build, not a mock-up)           │
│ All  ──●───── 0.5in       │                                                  │
│ ☐ Set each separately     │                                                  │
│ SPACING                   │                                                  │
│ All  ──●───── 0pt         │                                                  │
│ ONE PAGE                  │                                                  │
│ ☑ Fit to one page         │                                                  │
│ SHOW IN PDF               │                                                  │
│ ▾ ☑ Education          1  │                                                  │
│ ▾ ☑ Experience         1  │                                                  │
│ …                         │                                                  │
│ CHECKS                    │                                                  │
└───────────────────────────┴──────────────────────────────────────────────────┘
```

### 3.3 The top bar

**Status chips** update after every rebuild:

| Chip | Meaning |
|------|---------|
| green `1 page` | The PDF is exactly one page. |
| red `2 pages: overflow` | It spills onto a second page. See [Fit to one page](#36-fit-to-one-page) and the Checks list for where it starts. |
| `ATS 14/14` | The name, email, section headings and every school/company/project name were found in the PDF's text, in reading order. Red if any is missing or out of order. |
| yellow `35 placeholders` | Text still in `[brackets]`. The list is under **Checks**. |
| yellow `Fitted 31%` | Fit to one page shrank the layout to make it fit. Hover for the exact font, margins and spacing used. |
| grey `393 ms` | How long the last build took. |
| red `Build error` | The LaTeX build itself failed. The message is shown over the preview. |

**Buttons:**

| Button | What it does |
|--------|--------------|
| **Final** (checkbox) | Applies to **Export PDF** only: refuse to export while any `[placeholder]` remains. |
| **Revert** | Throw away your unsaved changes and go back to the last saved state. Greyed out when nothing has changed. |
| **Save style** | Write your changes into `resume.json` (see [3.5](#35-saving-reverting-and-exporting)). Greyed out when nothing has changed. |
| **Export PDF** | Run the full checks on what you see now and write `dist/Resume.pdf` if they pass. |

### 3.4 The controls, one by one

Every slider is a normal browser slider: click and drag, or click it and use the arrow keys. A small
**↺** appears next to any slider that isn't at its default; click it to reset just that one.

**Template.** Which `.tex` layout to use: `Jake's Resume` (the current look) or
  `Jake's Resume, icon header` (bold headings, an icon-based contact line). Both use the same font,
  size, margin and spacing controls below.

**Font.** A dropdown in two groups. *Bundled* fonts (Latin Modern, TeX Gyre Termes, Pagella, Heros) build on
  any machine. *Installed on this computer* fonts (Times New Roman, Georgia, Charter, Helvetica, Arial,
  Avenir; mostly a macOS thing) use your computer's copy. Those have no small caps, so section headings switch to normal
  case, and a machine without the font can't rebuild the PDF.

**Text size.** 8 to 14 pt. The default is 11 pt. Everything scales with it (name, headings, bullets).

**Margins.** One **All** slider moves all four sides together (0.25 to 1.5 in, default 0.5). Tick **Set each
  separately** to get **Top / Bottom / Left / Right** sliders. Unticking it again makes all four
  equal to the first one (Top). Spacing works the same way, and unticking it makes all three equal
  to Sections.

**Spacing.** Extra space added to the template's own spacing, from -3 pt (tighter) to +6 pt (looser). **All**
  moves the three together; tick **Set each separately** for **Sections** (before each heading),
  **Entries** (before each school, job or project) and **Bullets** (after each bullet).

**One page → Fit to one page.** When ticked (the default), an overflowing page is shrunk automatically. Your sliders are never
  moved by it.

**Show in PDF.** A tree of everything in your resume. Each **section** has a checkbox and its entry count. Click
  the small triangle to open a section, then an entry:
  - the entry's checkbox shows or hides the whole entry;
  - each **field** (location, degree, gpa, date, …) has its own checkbox with a grey preview of its
    text (hover for the full text);
  - **all bullets** hides every bullet at once, and **bullet 1, bullet 2, …** hide them one by one.

  Unticking a section dims its entries. Unticking **all bullets** greys out the individual bullet
  boxes. The name of an entry (school, company, project name, organization, skill label) has no
  checkbox of its own: hide the whole entry instead.

**Checks.** Details behind the chips: the page-count result (with where an overflow starts), the fit that was
  applied, any ATS problems, and every remaining `[placeholder]` with where it is.

### 3.5 Saving, reverting and exporting

The UI keeps a **working copy** of your style and visibility choices. What each button touches:

| Action | Changes `resume.json` | Changes `dist/` PDF |
|--------|:---------------------:|:-------------------:|
| Moving any control | no | no |
| **Save style** | **yes** (style + hide flags only) | no |
| **Revert** | no | no |
| **Export PDF** | no | **yes, only if all checks pass** |
| `uv run build.py` in a terminal | no | yes, if all checks pass |

Details worth knowing:

- **Save style** re-reads `resume.json` first and changes only the `style` block and the hide flags
  (`hidden`, `hide`, `hide_bullets`). Your text is never touched, and edits you made in your editor
  while the page was open are kept. The file is rewritten with standard 2-space indentation, so blank
  lines you added by hand are dropped; key order is kept. Hiding a whole section changes it from a
  plain list to `{"hidden": true, "entries": [...]}`, and showing it again changes it back.
- **Save style** refuses to write anything that wouldn't build, and tells you why.
- **Export PDF** uses **what you see now, saved or not**, including any fit-to-one-page shrink. The
  terminal command `uv run build.py` builds from the **saved** file. Press **Save style** first if
  you want both to match.
- Preview PDFs live in `build/preview/` (git-ignored, the last three are kept). Exporting is the only
  way the UI writes into `dist/`.

### 3.6 Fit to one page

When the preview overflows and **Fit to one page** is on:

1. The overflowing build shows first (red `2 pages: overflow`), so you see what you changed.
2. If you then leave the controls alone for about a third of a second, the fit search starts on its
   own ("Fitting to one page…" appears over the preview). There is no button to press.
3. It searches for the **smallest** shrink that makes one page, moving font size, margins and spacing
   together, and never going below 10 pt text, 0.4 in margins and -2 pt spacing (a value you set even
   tighter is kept).
4. The PDF updates, and a yellow `Fitted N%` chip appears. Hover it for the exact numbers.

It takes roughly 3 to 5 seconds, is cancelled if you touch a control again, and only ever affects the
build, not your saved settings. If it can't fit even at the floor, the Checks list says so and shows
where the overflow starts; then hide something, shorten a bullet or lower the text size yourself.

Untick **Fit to one page** if you'd rather see the overflow and fix it by hand. The tick is saved
with **Save style** as `"fit_to_page"`.

### 3.7 Recipes

**Remove the graduation date, but keep the text.** Open **Show in PDF** → Education → the entry →
untick `date`. Press **Save style**.

**Try a different look.** Pick a font, then nudge Size and Margins. Watch the `1 page` chip: if it
turns red, either leave **Fit to one page** on or make room. Revert if you don't like it.

**Make the page fit a longer resume.** Order of preference: (1) leave Fit on; (2) untick a weak bullet;
(3) hide a whole entry; (4) tighten Spacing → Bullets to about -1 pt; (5) reduce Margins to 0.4 in.

**Tailor for one job.** Untick the entries and bullets that don't fit the role, press **Export PDF**,
then copy `dist/Resume.pdf` somewhere with a job-specific name. Press **Revert** to
return to your saved state (you never pressed Save, so nothing was changed). Note that Export
overwrites the same file name in `dist/`, so copy it out first. Saved per-job variants are
not built yet.

**Send-ready check.** Fill in your placeholders, tick **Final**, press **Export PDF**. If placeholders
remain, nothing is written and the message lists how many.

**Edit wording while the UI is open.** Edit `resume.json` in your editor. Text changes appear the next
time the preview rebuilds (touch any control). **Reload the page** afterwards so the tree and the field
previews show the new text. If you added or removed an entry, the page tells you to reload.

### 3.8 Messages and what to do

Messages appear as a red box over the preview, or a small dark pop-up at the bottom.

| Message | Meaning | Do this |
|---------|---------|---------|
| `resume.json needs fixing before the UI can load it: …` | `resume.json` has an error (the text says which entry and field). | Fix it in your editor, then press **Reload page**. |
| `resume.json changed on disk since this page loaded. Reload the page.` | You added or removed an entry while the page was open. | Press **Reload page**. Unsaved UI changes are lost, so Save first next time. |
| `Saved style and visibility to resume.json` | Save worked. | Nothing. |
| `Exported dist/Resume.pdf` | Export passed every check. | Nothing. |
| `Not exported: dist/ left unchanged.` + reasons | A check failed (page count, ATS, or placeholders with **Final** on). | Read the reasons; `dist/` still holds your last good PDF. |
| `Could not save: …` | The change would make `resume.json` invalid. | Read the reason and undo that change. |
| `Build error` chip + LaTeX output | The LaTeX build failed. | Usually a font that isn't installed on this machine: pick a bundled font. |

### 3.9 What the UI doesn't do

- It doesn't edit your text. Use your editor (see [section 4](#4-editing-your-content-resumejson)).
- It doesn't save named variants or presets (planned, not built).
- It isn't combined with `--watch` (the two flags are separate modes). You can run `--watch` in a
  second terminal, but it rebuilds `dist/` every time `resume.json` changes, which includes each
  **Save style**.

---

## 4. Editing your content (`resume.json`)

Type plain text. The characters `& % $ # _ { } ~ ^ \` are escaped for you, so `cut errors 80%` just
works. Sections, in order: `basics`, `education`, `experience`, `projects`, `skills`, `leadership`.

| Section | Entry fields |
|---------|--------------|
| `basics` | name, location, citizenship, phone, email, linkedin_url, linkedin_label, github_url, github_label |
| `education` | school, location, degree, gpa, date, bullets |
| `experience` | company, location, title, dates, bullets |
| `projects` | name, tech, date, bullets |
| `skills` | label, items |
| `leadership` | organization, location, role, dates, bullets (heading: "Leadership / Extracurricular") |

- **Optional fields** (`citizenship`, `phone`, the LinkedIn/GitHub pairs, `gpa`, `tech`, and a
  leadership entry's `location`): leave them out, or empty, and they disappear from the PDF.
- A URL and its label must be given together (both or neither).
- Field-name typos and missing required fields are reported with the entry and field they belong to,
  for example `education > entry #1 ("Example State University") > date: required field is
  missing`.

### Inline markup (inside any string)

| Write | You get |
|-------|---------|
| `**bold**` | **bold** |
| `*italic*` | *italic* |
| `--` | an en dash (`May 2025 -- Present`) |
| `[anything here]` | a **placeholder**: red, with the brackets kept (black under `--final`) |
| `~80%` | "∼80%": a `~` right before a digit means "approximately" |

Escaping happens first and markup second, so `100% & $5 #1 under_score` is safe to type.

### The placeholder workflow

Unfinished facts go in `[brackets]`, for example `used daily by [N] staff`. They show in red in the
preview, are counted in the yellow chip and listed under **Checks**. The build still succeeds while
they exist. `uv run build.py --final` (or **Final** + **Export PDF**) refuses to build until every
one is filled in. Placeholders inside hidden content don't count.

---

## 5. Hiding things

Everything below keeps your text in the file; it just leaves it out of the PDF. The UI's **Show in
PDF** tree writes exactly these forms when you press **Save style**.

**A whole entry:**

```json
{ "name": "Campus Map CLI", "hidden": true, "tech": "...", "date": "...", "bullets": [] }
```

**A whole section** (write it as an object instead of a plain list):

```json
"projects": { "hidden": true, "entries": [ ... ] }
```

**One field of an entry:**

```json
{ "school": "...", "degree": "...", "date": "Expected May 2027", "hide": ["date"], "bullets": [ ... ] }
```

**Particular bullets** (1-based, the same numbers error messages use), or all of them:

```json
"hide_bullets": [2, 3]
"hide": ["bullets"]
```

Any field can be hidden **except the one that names the entry** (`school`, `company`, `name`,
`organization`, `label`): the ATS check looks for it in the PDF. Hide the whole entry instead.
Hidden content is ignored by the page-count, ATS and placeholder checks, and a section with nothing
visible loses its heading.

---

## 6. Style reference

The optional `style` block. Every default reproduces the original layout exactly, so leave out what
you don't change. The UI writes the whole block at the end of `resume.json` when you save.

```json
"style": {
  "template": "icons",
  "font": "pagella",
  "font_size": 10.5,
  "margins": { "top": 0.5, "bottom": 0.5, "left": 0.6, "right": 0.6 },
  "section_gap": 0,
  "entry_gap": -0.5,
  "bullet_gap": 0,
  "fit_to_page": true
}
```

| Key | Range | Default | Effect |
|-----|-------|---------|--------|
| `template` | see below | `default` | The .tex layout |
| `font` | see below | `default` | Typeface |
| `font_size` | 8 to 14 pt | 11 | Text size |
| `margins.top/bottom/left/right` | 0.25 to 1.5 in | 0.5 each | Page margins |
| `section_gap` | -3 to 6 pt | 0 | Extra space before each section heading |
| `entry_gap` | -3 to 6 pt | 0 | Extra space before each entry |
| `bullet_gap` | -3 to 6 pt | 0 | Extra space after each bullet |
| `fit_to_page` | true / false | true | Shrink to one page when it overflows |

**Templates**

| `template` | Layout | Section headings | Contact line |
|------------|--------|-------------------|--------------|
| `default` | Jake's Resume | small caps | plain text, `\|`-separated |
| `icons` | Jake's Resume, icon header | **bold** small caps | icons (📞 ✉ in LinkedIn/GitHub too) |

Both are the same underlying content and font/margin/spacing machinery — they share the same
custom LaTeX macros (`templates/_macros.tex.j2`) and the same per-section rendering
(`templates/_sections.tex.j2`), so every knob above works identically on either one. Adding a
template means adding one `templates/<name>.tex.j2` file that provides its own preamble and header
block and reuses those two shared files; it isn't a separate content model, and it doesn't need its
own `resume.json`.

**Fonts**

| `font` | Typeface | Builds on any machine? | Small-caps headings |
|--------|----------|:----------------------:|:-------------------:|
| `default` | Latin Modern (the original look) | yes | yes |
| `termes` | TeX Gyre Termes (Times-like) | yes | yes |
| `pagella` | TeX Gyre Pagella (Palatino-like) | yes | yes |
| `heros` | TeX Gyre Heros (Helvetica-like) | yes | yes |
| `times-new-roman`, `georgia`, `charter`, `helvetica`, `arial`, `avenir` | the copy installed on your computer | no, needs the font installed | no (normal case) |

**About the spacing sliders.** The template only fits on one page because TeX squeezes its list
spacing to the limit, so a small spacing change can look like it did nothing until there is room to
spare. The gaps are still exact (in a roomier layout each 1 pt shows up as 1 pt); the squeeze just
absorbs them. This is also why **Fit to one page** exists.

---

## 7. Command line reference

```sh
uv run build.py [--final] [--no-fit]     # build once
uv run build.py --watch [--final]        # rebuild whenever resume.json or the template changes
uv run build.py --serve [--port N]       # the live web UI
```

| Flag | Effect |
|------|--------|
| *(none)* | Build, run the checks, write `dist/` if they pass. Shrinks to fit if the page overflows. |
| `--final` | Fail if any `[placeholder]` remains; placeholders render black instead of red. |
| `--no-fit` | Don't shrink. An overflowing page fails with a report of where it starts. |
| `--watch` | Rebuild on every save of `resume.json` or the template. Ctrl+C stops it. |
| `--serve` | Start the web UI (see [section 3](#3-the-web-ui)). |
| `--port N` | Port for `--serve` (default 8000). |
| `-h` | Show the built-in help. |

Exit code is 0 when the build passed, 1 when it failed, which makes it usable in scripts.

**Typical terminal output:**

```
== Building resume ==
Page count:
  PASS  page count: 1
ATS text check (PDF text, reading order):
  PASS  name: Alex Rivera
  PASS  heading: Education
  ...
Placeholders:
  INFO  35 placeholder(s) remaining:
          [N]      Experience > Acme Logistics > bullet #1
OK  dist/Resume.pdf
```

When fit-to-one-page had to act, the page count block adds a line such as
`Fit to 1 page: squeeze 31% (font 10.7pt, margins 0.47in, gaps -0.6pt)`.

---

## 8. What the checks mean

Every build runs three checks. If any **fails**, `dist/` is left untouched and the attempt is kept in
`build/resume.pdf` so you can look at it.

**Page count.** The PDF must be exactly one page. If it isn't, the report names the section where the
overflow starts, the entries that landed on page 2, and how many lines spilled.

**ATS text check.** Applicant-tracking systems read the *text* inside the PDF, not the picture. The
check extracts that text and confirms the name, email, each section heading and each school, company,
project and organization name appears, in the right reading order. This catches fonts or layouts that
scramble extraction.

**Placeholders.** Lists every `[bracketed]` item still in visible content, and where. Informational,
unless you use `--final`, where any remaining placeholder fails the build.

**Fit to one page** (not a check, but part of the build) shrinks font, margins and spacing together,
just enough. It never rewrites `resume.json`. If even the smallest setting (10 pt, 0.4 in, -2 pt)
overflows, the build fails and says so.

---

## 9. Troubleshooting

| Problem | Cause and fix |
|---------|---------------|
| `error: tectonic not found` | `brew install tectonic`. |
| `resume.json has N problem(s): …` | Each line names the entry and field. Common: a missing required field, a typo in a field name, a trailing comma, an unescaped `"` inside a string. |
| The page count is red (2 pages) | Leave **Fit to one page** on, or hide/shorten something. The Checks list shows where the overflow starts. |
| Spacing sliders seem to do nothing | The page is nearly full, so TeX absorbs small changes. Make room first (smaller text, hide a bullet), or rely on Fit. |
| Section headings changed from small caps to normal case | You picked one of the system-installed fonts, which have no small caps. Use a bundled font to get them back. |
| `Build error` after choosing a font | That font isn't installed on this machine. Choose a bundled one. |
| `Address already in use` when starting the UI | Something already uses port 8000: `uv run build.py --serve --port 9000`. |
| The preview frame is blank | The preview uses your browser's built-in PDF viewer; make sure it's enabled, or try another browser. |
| The UI says "changed on disk" | You added or removed an entry while it was open. Press **Reload page**. |
| A hidden field's placeholder still blocks `--final` | It shouldn't: hidden fields are ignored. Check that the name in `hide` is spelled exactly like the field (`date`, not `dates`). |
| `'school' names this entry and can't be hidden` | Entry names can't be hidden (the ATS check needs them). Use `"hidden": true` on the entry. |
| `hide_bullets has 9, but this entry has 2 bullet(s)` | Bullet numbers are 1-based and must exist. |
| `style > font: unknown font '…'` | Use one of the keys in the font table above. |
| `style > template: unknown template '…'` | Use one of the keys in the templates table above (`default` or `icons`). |
| `style > margins > top: Input should be greater than or equal to 0.25` | The value is outside the allowed range in the style table. |
| Nothing new in `dist/` | The build failed a check; the reasons are printed (or shown in the red box). `dist/` keeps the last good PDF. |

---

## 10. Project layout

```
resume.json                YOUR content + style + visibility (git-ignored; created from the sample on first run)
resume.example.json        the sample resume that resume.json starts from
build.py                   the build, the checks, fit-to-one-page, and the command line
layout.py                  turns the style into LaTeX (fonts, margins, spacing, the fit squeeze)
models.py                  validates resume.json with readable errors
server.py                  the web UI's local server
web/                       the web UI (index.html, app.css, app.js: plain files, no build step)
templates/resume.tex.j2    the "default" layout, as a template
templates/resume-icons.tex.j2  the "icons" layout, as a template
templates/_macros.tex.j2   custom LaTeX commands shared by every template
templates/_sections.tex.j2 per-section content rendering shared by every template
build/                     scratch output (git-ignored); build/preview/ holds UI previews
dist/                      finished PDFs (git-ignored)
```

**Requirements:** [Tectonic](https://tectonic-typesetting.github.io) and
[uv](https://docs.astral.sh/uv/) (`brew install tectonic uv`). Python 3.12+ and the packages
(Jinja2, Pydantic, pypdf, watchfiles, FastAPI, Uvicorn) are installed by `uv run`.

**Design rule:** with default style and no hide flags, the output is identical to the original
hand-written layout. Every new option starts switched off, so an untouched `resume.json` builds exactly
as it always did.

**Not built yet:** saved presets and per-job variants (a named set of hidden entries plus style,
exported as its own PDF).

---

## 11. License and credits

MIT, see [LICENSE](LICENSE). The LaTeX templates are adapted from
[Jake's Resume](https://github.com/jakegut/resume) by Jake Gutierrez (MIT).
