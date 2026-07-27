# Acknowledgments

MyPaiOS is MIT-licensed (see [`LICENSE`](LICENSE)). **This file, together with
[`NOTICE`](NOTICE) and the full texts in [`licenses/`](licenses/), carries every
third-party notice MyPaiOS is obliged to pass on** — for code, icons, fonts,
emoji artwork and data that is copied into, bundled with, or served by this
repository.

Three principles govern what is written here:

1. **Accuracy over completeness theatre.** Every claim below is meant to be
   checkable. Where something could not be verified, it says so rather than
   guessing. Where an earlier revision of this file was wrong, the correction
   is stated plainly rather than quietly edited away.
2. **Nothing here is a claim of endorsement.** Naming a project, product,
   model or company does not imply it endorses, sponsors or is affiliated with
   MyPaiOS. See [Trademarks](#trademarks).
3. **Distribution shape matters.** MyPaiOS is distributed as **source**. Most
   of the packages listed here are installed by *you*, from PyPI/npm, into
   *your* environment — MyPaiOS redistributes none of their code, so
   permissive licences (MIT/BSD/ISC/Apache-2.0/PSF) impose no notice duty on
   this repository. Those entries are here for transparency. The items that
   genuinely *are* redistributed — vendored front-end bundles, inline icon
   artwork, fonts, the emoji proxy, and packaged desktop builds — are the ones
   whose notices are mandatory, and they are called out as such.

If you believe something here is mis-attributed or missing, please open an
issue — it will be corrected promptly.

### How to keep this current

When you change what the project ships, update this file **in the same commit**:

| If you… | Then… |
|---|---|
| add or update a file in `static/lib/` or `static/libs/` | add/refresh its row *and* enumerate anything the bundle statically includes; record the upstream URL, version and `sha256` so the next audit is one command |
| paste an SVG icon in from an icon set | make sure that set is credited under [Icons](#icons); a new set needs a new row **and** a `licenses/` file |
| add a font to `static/fonts/` | add a row under [Fonts](#fonts) and copy its licence text into `licenses/`, with the copyright line taken from the font's own `name` table — not from the filename |
| add a pip/npm dependency | add it to the relevant dependency table (and to `requirements*.txt` / `package.json`). No `licenses/` file is needed for permissive packages we merely import |
| add a model, model catalog entry, or one-click installer | add it under [AI model weights](#ai-model-weights-downloaded-at-runtime-never-bundled) or [Packages the Cookbook installs](#packages-the-cookbook-installs-on-your-behalf) **with its licence**, flagging anything non-commercial or non-OSI |
| shell out to a new system binary | add it under [System binaries and companion services](#system-binaries-and-companion-services) |
| adapt third-party code | add it under [Adapted / borrowed code](#adapted--borrowed-code), copy the licence into `licenses/`, and put a provenance header in the file — including an explicit change notice if the licence is Apache-2.0 (§4(b)) |
| publish a container image or desktop build | read [Before publishing a binary artifact](#before-publishing-a-binary-artifact) first — obligations that are dormant for a source release become live for an artifact |

---

## Foundation: Odysseus

MyPaiOS is a fork of **Odysseus** (Copyright © 2025 Odysseus Contributors),
forked at the MIT-licensed snapshot (upstream commit
`8354948a1cfa5afba3fc90ce02b9435405ba5f37`, 2026-06-05, authored by
`nubs <nubs@nubs.site>`). Upstream later relicensed to AGPL-3.0-or-later
(2026-06-09); **no post-fork upstream code is included** — everything inherited
here comes from the MIT snapshot and remains under the MIT License. See
[`NOTICE`](NOTICE) and [`LICENSE`](LICENSE), which carries both copyright lines.

**Most of this codebase is Odysseus's work, and that should be said plainly.**
Measured against the fork point (all figures reproducible with `git` at the time
of writing):

| | |
|---|---|
| Files inherited from Odysseus | **877 of 1030** — of which **626 are byte-identical** to upstream |
| Files added by MyPaiOS | 153 |
| Upstream files deleted | 34 |
| Commits after the fork point | **31 of 929** |
| Upstream lines surviving in the 251 inherited files that were touched | **~99%** (+5,452 / −1,859 against 214,343 upstream lines) |
| Lines authored by MyPaiOS | **≈26,800 of ≈418,800 (~6%)** |

*Method for the last row: `wc -l` over all tracked files excluding vendored
libraries, minified bundles, lockfiles, generated data snapshots and
`licenses/`; MyPaiOS's share = lines in the 134 new files in that set, plus
insertions into inherited files. Counting every tracked file instead gives
≈40,400 of ≈473,200 (~9%).*

What MyPaiOS added post-fork: the Crew multi-agent supervisor
(`services/crew/`), the detached Code-tab job runner (`services/code/`), Mail
Guard (`services/mailguard/`), local video analysis (`services/video/`), the
agentic browser tool (`services/browser/`), the Artifacts runtime, the Agents
hub and template gallery, the layered PriceBook (`services/pricing/`), the
Activity / panel-coordinator UI layer, the Telegram gateway, the Electron
desktop shell, the `scripts/paios-*` CLI suite, the Claude/Codex integration
bundles, and this attribution record.

Everything else — the chat engine, agent loop, tool protocol, Deep Research
engine, Cookbook/hwfit, the email/calendar/contacts stack, notes, gallery,
memory and skills subsystems, and essentially all of the front-end — is
Odysseus's.

**Inherited media.** The screenshots and screen recordings in `docs/`
(`paios.jpg`, `bg.webm`, `chat.*`, `compare.*`, `document.*`, `gallery.webm`,
`notes.*`, `research.*`, `theme.webm` — 14 files, ~17 MB) were recorded by the
Odysseus authors and arrived with the MIT snapshot (upstream commit `e5c99a5`,
"Odysseus v1.0"). `docs/paios.jpg` is upstream's `docs/odysseus.jpg`, renamed by `b6210a6`; the
clips still display the Odysseus name, sailboat logo and the tagline "Yours
for the voyage." **None of these 14 files are referenced by the README or
`docs/index.html` any more** (both were rebuilt with MyPaiOS's own screenshots
and an original animated banner) — the files remain on disk, unreferenced,
pending the re-recording in [Known open items](#known-open-items) item 3.
Copyright © 2025 Odysseus Contributors, MIT License. "Odysseus" and its logo
are the upstream project's marks; they appear here only because these are
upstream's own screenshots. See [Known open items](#known-open-items).

---

## Adapted / borrowed code

Portions of this project were adapted from other open-source repositories.
Their original authors retain copyright over the adapted portions, under the
licences noted below. Full texts are in [`licenses/`](licenses/).

> **Note on provenance.** Every adaptation in this section was made **upstream
> in Odysseus**, before the MyPaiOS fork point (commit `8354948`). MyPaiOS
> inherited them and has expanded their attribution; it does not claim to have
> authored the adaptations. Earlier revisions of this file and of the affected
> source headers credited "MyPaiOS contributors (2026)" with the porting and
> extraction work — that was wrong, and `git` shows it: `src/copilot.py` and
> `src/goal_based_extractor.py` (including `EXTRACTOR_PROMPT`) already existed
> at the fork point, and `services/hwfit/__init__.py` was an *empty* file
> upstream while the rest of `services/hwfit/` predates the fork unchanged.
> The headers have been corrected.

- **[opencode](https://github.com/anomalyco/opencode)** — open-source AI coding
  agent (originally
  [opencode-ai/opencode](https://github.com/opencode-ai/opencode), archived
  Sep 2025). Copyright © 2025 opencode. **MIT License.**
  Upstream Odysseus declared this project *"adapted for agent-loop /
  tool-execution patterns and UI concepts"*, and that declaration is preserved
  here in full — an earlier revision of this file narrowed it to "inspired by,
  no code copied", which is not a retraction MyPaiOS is in a position to make
  about code it did not write. Specifically identified: the GitHub Copilot
  provider integration in `src/copilot.py` (device-flow auth, model-picker and
  per-request flag logic) is a Python port of opencode's Copilot
  implementation. Full text in
  [`licenses/opencode-MIT-LICENSE.txt`](licenses/opencode-MIT-LICENSE.txt).
- **[llmfit](https://github.com/AlexsJones/llmfit)** by **Alex Jones** — the
  engine behind the Cookbook's model download / serve / "What Fits?" feature.
  Copyright © Alex Jones. **MIT License.** Adapted (upstream, in Rust → Python)
  in `services/hwfit/` — hardware detection, quant-aware fit scoring and the
  model catalog; `services/hwfit/fit.py` reproduces llmfit's use-case weights
  directly — plus `routes/cookbook_*.py`, `routes/hwfit_routes.py`,
  `static/js/cookbook*.js` and `scripts/paios-cookbook`. Full text in
  [`licenses/llmfit-MIT-LICENSE.txt`](licenses/llmfit-MIT-LICENSE.txt).
- **[Tongyi DeepResearch](https://github.com/Alibaba-NLP/DeepResearch)** by
  **Alibaba-NLP / Tongyi Lab** — Copyright © Alibaba-NLP / Tongyi Lab.
  **Apache-2.0.** Upstream Odysseus declared this project adapted for its Deep
  Research feature (`services/research/`, `src/research_handler.py`,
  `routes/research_routes.py`, `services/search/`), and that declaration is
  preserved here in full for the same reason as opencode's. Specifically
  identified: the goal-based content-extraction prompt in
  `src/goal_based_extractor.py` is taken near-verbatim from DeepResearch's
  `inference/prompt.py` (`EXTRACTOR_PROMPT`); the surrounding engine
  (`src/deep_research.py`) implements the IterResearch pattern that project
  published. Modified files carry change notices per Apache-2.0 §4(b). Full
  text in
  [`licenses/DeepResearch-Apache-2.0.txt`](licenses/DeepResearch-Apache-2.0.txt).
- **[talon](https://github.com/mailgun/talon)** by **Mailgun Technologies,
  Inc.** — **Apache License 2.0.** The multilingual quote-detection patterns in
  `static/js/emailLibrary/utils.js` (`_TALON_WROTE`, `_TALON_FROM`,
  `_TALON_SENT`, `_TALON_SUBJ`, `_TALON_TO`, `_TALON_ORIG_RE`) are **adapted
  from** talon's email quotation-parsing word lists and separator patterns,
  re-expressed as JavaScript regex source fragments and extended with
  additional locales (CJK, Cyrillic, Greek). Consumed by
  `static/js/emailLibrary.js` and `static/js/emailLibrary/signatureFold.js`.
  Modified per Apache-2.0 §4(b) — the file carries the change notice.
  *This credit was missing entirely until now, even though the source file's own
  comment acknowledged the borrowing.* Full text in
  [`licenses/talon-Apache-2.0.txt`](licenses/talon-Apache-2.0.txt).
  (talon's upstream LICENSE is the bare Apache-2.0 text with no filled-in
  copyright line; the holder above is taken from the project's ownership.)
- **[litellm](https://github.com/BerriAI/litellm)** by **BerriAI** — Copyright
  © 2023 Berri AI. **MIT License.** A filtered snapshot of litellm's community
  model-price database is bundled as
  `services/pricing/litellm_snapshot.json` — **721 models across 11 providers,
  fetched 2026-07-18**, normalized to USD per 1M tokens and consumed by
  `services/pricing/pricebook.py`. Only the MIT-licensed portion of the litellm
  repository is used; the separately-licensed `enterprise/` directory is not.
  The copyright line in
  [`licenses/litellm-MIT-LICENSE.txt`](licenses/litellm-MIT-LICENSE.txt) was
  re-verified against upstream and matches byte-for-byte.

### Inspired by (no code copied)

Named in source comments, and therefore named here — but genuinely
concept-level, so no licence text is shipped for them (doing so would overstate
the relationship):

- **[Aider](https://github.com/Aider-AI/aider)** by **Paul Gauthier** and
  contributors (Apache-2.0) — the repo-map idea behind
  `services/code/repomap.py`: give the model a token-budgeted map of the
  project's files and their key symbols instead of whole files. MyPaiOS's
  implementation is independent and pure-stdlib (`ast` + regex, no tree-sitter,
  no PageRank/graph ranking, a flat character budget); no Aider code is present.
- **Hermes skills format** by **Nous Research** — the `SKILL.md` shape used by
  MyPaiOS skills (YAML frontmatter plus a structured markdown body: When to Use
  / Procedure / Pitfalls / Verification) follows the convention Hermes
  published. Parser/writer in `services/memory/skill_format.py`, storage in
  `services/memory/skills.py`, script execution in
  `services/memory/skill_runner.py` — all independently implemented. A file
  format convention, not code.
- **Claude Agent Skills** (Anthropic) — the `SKILL.md` + `scripts/` packaging
  convention that `services/memory/skill_runner.py` and the interop bundles in
  `integrations/claude/skills/` and `integrations/codex/skills/` target. Format
  convention only; no Anthropic code is included.
- **Standards and reference data.** A few small lookup tables follow published
  references rather than inventing their own: the `AltGr` → `AltGraph` modifier
  mapping in `static/js/platform.js` follows the W3C UI Events specification (as
  documented on MDN), and the emoji shortcode names in
  `static/js/emojiShortcodes.js` follow GitHub's `:shortcode:` convention (the
  gemoji naming scheme, MIT) mapped to standard Unicode emoji. These are factual
  mappings between public standards; no third-party code or data file was
  copied. *Not independently re-derived: if that shortcode map turns out to have
  been generated from a gemoji-derived data file rather than hand-curated,
  gemoji (MIT, GitHub, Inc.) needs an explicit credit and a `licenses/` file.*

---

## Icons

MyPaiOS's interface is drawn almost entirely with **inline SVG icons**. Most of
them come from two open-source icon sets whose markup was pasted inline rather
than installed as a dependency — which is exactly why no licence file existed
for them until now. **These are notices MyPaiOS is obliged to carry**: the icon
paths are distributed in this repository and served to every user.

| Icon set | Author | Where | License | Text |
|---|---|---|---|---|
| [Feather Icons](https://github.com/feathericons/feather) | Cole Bemis | Inline SVGs across `static/index.html`, `static/js/**`, `static/login.html`, `static/style.css`, `docs/index.html`, `src/visual_report.py`, `MyPaiOS-Help-Guide.html`, `desktop-electron/loading.html` — `check`, `x`, `copy`, `chevron-down`, `eye`, `trash-2`, `send`, `search`, `settings`, `file-text`, `download`, `upload`, `bell`, … | MIT | [`licenses/feather-MIT-LICENSE.txt`](licenses/feather-MIT-LICENSE.txt) |
| [Lucide](https://github.com/lucide-icons/lucide) | Lucide Icons and Contributors | Inline SVGs across the same files plus `static/app.js` — including icons with **no Feather equivalent**: `bot`, `disc-album`, `git-compare`, `syringe`, `triangle-alert`, `circle-plus/minus`, `square-plus/minus`, `columns-2`, `keyboard`, `cylinder`, `phi`, `app-window-mac`, `monitor-stop`, `bolt`, `clock-4`, `clock-12`, `dice-1`, `disc-2`, `circle-question-mark`, `align-horizontal-justify-center`, and the rounded `pencil` | ISC | [`licenses/lucide-ISC-LICENSE.txt`](licenses/lucide-ISC-LICENSE.txt) |

**Feather Icons** — Copyright © 2013-2023 Cole Bemis. Many icons are used
verbatim; some are hand-modified variants or recombinations of Feather paths,
which remain derivative works of Feather and are covered by the same notice.

**Lucide** — Copyright © 2026 Lucide Icons and Contributors, ISC License. Lucide
is itself a fork of Feather, but it is an **independent** obligation here, not
one the Feather notice absorbs: a number of the Lucide icons in use have no
Feather counterpart at all. Lucide's LICENSE file is dual — the ISC grant, then
the list of icons it derives from Feather under the MIT License, Copyright ©
2013-present Cole Bemis. It is reproduced **in full** in
[`licenses/lucide-ISC-LICENSE.txt`](licenses/lucide-ISC-LICENSE.txt), so both
notices travel together.

*How this was checked (so it can be re-checked):* every path/polyline/polygon
primitive in the shipped inline SVGs was matched against
`feather-icons@4.29.2/dist/icons.json` and `lucide-static`'s `icon-nodes.json`.
**79 distinct Feather icons** (~660 occurrences) and **46 distinct Lucide
icons** (~143 occurrences) appear with *every* primitive byte-identical to
upstream; 22 of the Lucide ones exist only in Lucide. Some Lucide paths match
older releases rather than the current one — e.g. the rounded `pencil` path
`M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z` (8 uses), which is
old-Lucide's, not Feather's `edit-2`.

### Emoji

MyPaiOS renders emoji as monochrome line icons rather than colour glyphs. The
artwork is **OpenMoji**.

> All emojis designed by [OpenMoji](https://openmoji.org/) — the open-source
> emoji and icon project. License:
> [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)

`routes/emoji_routes.py` fetches OpenMoji's `black` line-art SVGs from
`cdn.jsdelivr.net/npm/openmoji@15.0.0/black/svg` on first use, caches them under
`data/emoji_cache/` (gitignored — **not** committed here), and re-serves them
same-origin from `/api/emoji/<codepoints>.svg`, where CSS uses them as a mask
tinted to the current text colour (`static/js/markdown.js`, `static/style.css`).

This is the one **copyleft** asset MyPaiOS actively distributes to its own
users, and it had no notice anywhere until now. CC BY-SA 4.0 §3(a) requires
creator identification, a copyright notice, a licence notice and link, a
warranty disclaimer, and an indication of modification wherever the material is
shared — and serving the SVGs to a browser is sharing. **The files are served
unmodified**: only colour is applied, at render time, via a CSS mask; the
distributed SVG is not altered. So the artwork is *used*, not adapted, and the
ShareAlike clause does not reach MyPaiOS's own MIT-licensed code — but it does
bind the emoji assets at every point of distribution.

OpenMoji is a project of HfG Schwäbisch Gmünd (initiated by Benedikt Groß and
Daniel Utz) with 50+ student and external contributors. Full licence text:
[`licenses/OpenMoji-CC-BY-SA-4.0.txt`](licenses/OpenMoji-CC-BY-SA-4.0.txt).
OpenMoji's separate build tooling (LGPL-3.0) is not used.

### Provider logos

The model picker shows a small vendor mark next to each model
(`static/js/providers.js`, rendered by `providerLogo()` into
`static/js/modelPicker.js` and `static/js/chat.js`). Those marks come from three
places:

| Source | Marks used | License | Text |
|---|---|---|---|
| [LobeHub Icons](https://github.com/lobehub/lobe-icons) | DeepSeek, Qwen | MIT (© 2023 LobeHub) | [`licenses/lobehub-icons-MIT-LICENSE.txt`](licenses/lobehub-icons-MIT-LICENSE.txt) |
| [Simple Icons](https://simpleicons.org) | Anthropic, Google Gemini, Meta, Mistral AI, X (xAI/Grok), Perplexity, NVIDIA | CC0-1.0 — public-domain dedication, no notice required | — |
| MyPaiOS (original) | Ollama, OpenRouter, OpenAI, Cohere, Microsoft/Phi, Zhipu/GLM, MiniMax, Moonshot/Kimi, Nous — simplified marks drawn for this project | MIT (this repo) | — |

The **LobeHub** credit is a real MIT obligation: the DeepSeek and Qwen `d`
attributes in `providers.js` were verified byte-identical to
`@lobehub/icons-static-svg`'s `deepseek.svg` and `qwen.svg` (the Qwen path is
LobeHub's, *not* Simple Icons'). The source file's own comment already said
"official whale logo from LobeHub icons" while no credit existed anywhere else.
The OpenAI mark is a hand-rounded redraw that matches neither Simple Icons nor
LobeHub byte-for-byte, so it carries no third-party copyright — only the
trademark consideration below.

These licences cover the **SVG renderings only**, never the underlying marks.

### Original artwork

The rest of MyPaiOS's visual identity is original to this project and covered by
this repository's MIT licence. Recorded so that no unnecessary credits get added
later — over-attribution is its own kind of inaccuracy:

- The **π mark** — generated from pure geometry by `scripts/make_pi_icon.py`
  (three rounded rectangles in PIL, no font and no third-party art), producing
  `static/icon-{32,192,512}.png`, `desktop-electron/assets/icon.png`,
  `icon.icns` and the macOS iconset. The π in `static/login.html` is the same
  mark drawn as three `<rect>`s. (Its CSS class `logo-boat` and the "falls back
  to the boat logo" comment in `static/index.html` are stale references to
  upstream Odysseus's sailboat mark, not to third-party art.)
- The eight **per-route favicons** in `static/index.html`.
- The **language / file-type glyphs** in `static/js/langIcons.js` — hand-drawn.
  Two are redraws of external marks: the Markdown "M↓" (the dcurtis
  markdown-mark, CC0 — no duty) and the Python double-snake (a PSF trademark —
  see [Trademarks](#trademarks)).
- The **animated background patterns** (synapse, rain, constellations,
  perlin-flow, petals, sparkles, embers) and all **theme palettes** in
  `static/js/theme.js`. The noise helper is the ubiquitous one-line value-noise
  hash `sin(x*12.9898 + y*78.233) * 43758.5453` — a de-minimis formula, not Ken
  Perlin's algorithm and not a copied noise library.
- The `.hljs-*` rules in `static/style.css` are an **original** theme mapped
  onto highlight.js's class names, not a copied highlight.js theme file.

No CSS framework or reset (normalize.css, Tailwind, Bootstrap) is used. Fonts
are served locally — MyPaiOS never contacts Google Fonts or any font CDN. No
Font Awesome, Heroicons, Bootstrap Icons, Tabler, Phosphor, Material Symbols,
Remix Icon, Iconoir or Boxicons artwork is present. The only base64 image in the
tree is a 1×1 transparent GIF inside the bundled `html2pdf.js`.

---

## Trademarks

MyPaiOS is an independent project. **It is not affiliated with, sponsored by, or
endorsed by any of the companies, projects or services named in this
repository**, and no endorsement is implied. It is also not affiliated with
Kwaai pAI-OS (paios.org), aurintex paiOS, or PayOS.

The vendor marks in `static/js/providers.js` are shown purely to identify which
model or endpoint you are talking to. **OpenAI**, **ChatGPT**, **GPT**,
**Codex** and **DALL·E**; **Anthropic**, **Claude** and **Claude Code**;
**Google**, **Gemini** and **Gemma**; **Meta** and **Llama**; **Mistral AI**,
**Mixtral**, **Codestral** and **Devstral**; **Alibaba**, **Tongyi** and
**Qwen**; **DeepSeek**; **xAI**, **Grok** and **X**; **Cohere** and
**Command R**; **Perplexity** and **Sonar**; **Nous Research** and **Hermes**;
**Microsoft**, **Azure**, **Microsoft 365**, **Visual Studio Code** and
**Phi**; **GitHub** and **GitHub Copilot**; **Zhipu AI / Z.AI**, **GLM** and
**ChatGLM**; **MiniMax**; **Moonshot AI** and **Kimi**; **NVIDIA** and
**Nemotron**; **IBM**, **Granite** and **Docling**; **Black Forest Labs** and
**FLUX**; **Stability AI** and **Stable Diffusion**; **Lightricks** and
**LTX-Video**; **Tencent** and **Hunyuan**; **Hugging Face**; **Ollama**;
**OpenRouter**; **Groq**; **Together AI**; **Fireworks AI**; **Venice AI**;
**Telegram**; **Obsidian**; **Home Assistant**; **Vaultwarden**; **Gitea**;
**Miniflux**; **Linkding**; **FreshRSS**; **SearXNG**; **DuckDuckGo**;
**Brave**; **Tavily**; **Serper**; and **Python** (whose logo is simplified in
`static/js/langIcons.js`) are the trademarks of their respective owners, used
**nominatively** to identify their products and services.

The built-in themes named `gpt`, `claude`, `claude-light` and `antigravity`
(`static/js/theme.js`) are colour palettes chosen to feel familiar to users of
those products. They are not affiliated with or approved by OpenAI, Anthropic or
Google, and no product artwork or code from those interfaces is included.
Colour values are not copyrightable; the product names used as theme keys are
third-party marks.

Some logo SVGs come from [Simple Icons](https://simpleicons.org) (CC0-1.0) and
[LobeHub Icons](https://github.com/lobehub/lobe-icons) (MIT); those licences
cover the SVG renderings only, never the underlying marks. "Odysseus" and its
sailboat logo are the upstream project's marks.

---

## Fonts

Bundled in `static/fonts/`; licence texts in [`licenses/`](licenses/). Both
families ship **unmodified and under their original names**, and neither
declares a Reserved Font Name, so OFL-1.1 §3/§5 renaming duties do not apply.
Copyright lines below were read from the font binaries' own `name` tables and
match the licence files byte-for-byte.

| Font | Version | License | Copyright / designers | Text |
|---|---|---|---|---|
| [Fira Code](https://github.com/tonsky/FiraCode) | 6.002 | SIL Open Font License 1.1 | "Copyright 2014-2021 The Fira Code Project Authors" — designers Carrois Corporate, Edenspiekermann AG, Nikita Prokopov | [`licenses/FiraCode-OFL-1.1.txt`](licenses/FiraCode-OFL-1.1.txt) |
| [Inter](https://github.com/rsms/inter) | 4.001 | SIL Open Font License 1.1 | "Copyright 2016 The Inter Project Authors" — designer Rasmus Andersson | [`licenses/Inter-OFL-1.1.txt`](licenses/Inter-OFL-1.1.txt) |

Both are self-hosted. Fira Code is the app-wide default (`FONT_MAP.mono` in
`static/js/theme.js`); Inter is the sans option and the default face for the
`claude` / `claude-light` themes.

**Correction — GohuFont.** Earlier revisions of this file, of `NOTICE`, and a
file `licenses/GohuFont-WTFPL.txt` credited **"GohuFont / WTFPL / Hugo
Chargois"** for `static/fonts/custom/GohuFont.ttf`. **That attribution was
false and has been removed.** The file is not GohuFont: its own `name` table
reads family `Untitled1`, copyright `"Copyright (c) 2025, Unknown"`, unique ID
`"FontForge 2.0 : Untitled1 : 1-3-2025"`, with **3 glyphs in 1,468 bytes** — an
empty FontForge placeholder that arrived with the upstream Odysseus snapshot and
is referenced by nothing in the codebase. It carries no licence grant of any
kind. Apologies to Hugo Chargois, who did not write it. The real GohuFont *is*
WTFPL-licensed; if it is ever genuinely wanted here, vendor it from
<https://font.gohu.org/> and restore a correct row and licence file then.

`static/fonts/custom/` is the drop-in directory for user-supplied fonts —
`routes/font_routes.py` lists whatever is there and the Theme panel offers it in
the Font dropdown. The placeholder above is still present on disk and would
appear in that dropdown as a broken 3-glyph font; see
[Known open items](#known-open-items).

---

## Bundled front-end libraries

Vendored and served directly — **these are redistributed, so their notices are
mandatory.** Several are *bundles* that statically include further third-party
packages whose notices minification destroyed; those are enumerated in the
second table. Versions were confirmed by `sha256` against upstream artifacts
(2026-07) and are recorded in each licence file so the next audit is one
command.

Vendored in `static/lib/`:

| Library | Purpose | License | Text |
|---|---|---|---|
| [highlight.js](https://github.com/highlightjs/highlight.js) **v11.9.0** | Code syntax highlighting | BSD-3-Clause (© 2006 Ivan Sagalaev) | [`licenses/highlightjs-BSD3.txt`](licenses/highlightjs-BSD3.txt) |
| [SheetJS / xlsx](https://github.com/SheetJS/sheetjs) **v0.20.3** (`xlsx.full.min.js`, from cdn.sheetjs.com) | Spreadsheet (`.xlsx`) read/write; the `full` build inlines SheetJS's own js-codepage (cptable 1.15.0), js-cfb and SSF | Apache-2.0 (© 2013-present SheetJS LLC) | [`licenses/xlsx-SheetJS-Apache-2.0.txt`](licenses/xlsx-SheetJS-Apache-2.0.txt) |
| [docx](https://github.com/dolanmiu/docx) **v8.5.0** (`docx.umd.min.js`) | Generate `.docx` documents | MIT (© 2016 Dolan) | [`licenses/docx-MIT-LICENSE.txt`](licenses/docx-MIT-LICENSE.txt) |
| [mammoth.js](https://github.com/mwilliamson/mammoth.js) **v1.8.0** (`mammoth.browser.min.js`) | Convert `.docx` → HTML | BSD-2-Clause (© 2013 Michael Williamson) | [`licenses/mammothjs-BSD2.txt`](licenses/mammothjs-BSD2.txt) |
| [html2pdf.js](https://github.com/eKoopmans/html2pdf.js) **~0.10.2** (`html2pdf.bundle.min.js`) | HTML → PDF export | MIT (© Erik Koopmans) — bundle contents are **not** all MIT, see below | [`licenses/html2pdfjs-MIT-LICENSE.txt`](licenses/html2pdfjs-MIT-LICENSE.txt) + [`licenses/html2pdf-bundle-LICENSE.txt`](licenses/html2pdf-bundle-LICENSE.txt) |
| [node-qrcode](https://github.com/soldair/node-qrcode) (`qrcode.min.js`) | QR-code rendering (2FA setup) | MIT (© 2012 Ryan Day) | [`licenses/node-qrcode-MIT-LICENSE.txt`](licenses/node-qrcode-MIT-LICENSE.txt) |

Vendored in `static/libs/artifacts/` for the Artifacts preview runtime
(`routes/artifact_routes.py`):

| Library | Purpose | License | Text |
|---|---|---|---|
| [React](https://github.com/facebook/react) **v18.3.1** (`react.production.min.js`) | Artifact React rendering | MIT (© Meta Platforms, Inc. and affiliates) | [`licenses/react-MIT-LICENSE.txt`](licenses/react-MIT-LICENSE.txt) |
| [ReactDOM](https://github.com/facebook/react) **v18.3.1** (`react-dom.production.min.js`) | Artifact React DOM mounting; **embeds a custom Modernizr 3.0.0pre build** (MIT, The Modernizr Team) whose banner is visible in the file | MIT | (same file) |
| [@babel/standalone](https://github.com/babel/babel) **v7.26.4** (`babel.min.js`) | In-browser JSX/ES transpilation | MIT (© 2014-present Sebastian McKenzie and other contributors) | [`licenses/babel-standalone-MIT-LICENSE.txt`](licenses/babel-standalone-MIT-LICENSE.txt) |

### Libraries bundled inside the vendored bundles

Minification stripped every one of these notices. They are reproduced in the
licence files listed.

| Library | Bundled inside | License | Text |
|---|---|---|---|
| [JSZip](https://github.com/Stuk/jszip) **v3.10.1** | `docx.umd.min.js`, `mammoth.browser.min.js` | **MIT OR GPL-3.0-or-later — used under MIT** | [`licenses/jszip-MIT-LICENSE.txt`](licenses/jszip-MIT-LICENSE.txt) |
| [pako](https://github.com/nodeca/pako) | `docx.umd.min.js`, `mammoth.browser.min.js` (via JSZip) | MIT AND Zlib (© 2014-2017 Vitaly Puzrin, Andrei Tuputcyn; zlib sources © Jean-loup Gailly, Mark Adler) | [`licenses/pako-MIT-Zlib.txt`](licenses/pako-MIT-Zlib.txt) |
| readable-stream, buffer, ieee754, inherits | `docx.umd.min.js` | MIT / MIT / **BSD-3-Clause** / **ISC** | [`licenses/docx-MIT-LICENSE.txt`](licenses/docx-MIT-LICENSE.txt) |
| underscore 1.13.1, bluebird, @xmldom/xmldom, xmlbuilder, lop, option, dingbat-to-unicode, base64-js, readable-stream, set-immediate-shim, lie, immediate, buffer, ieee754, isarray, inherits | `mammoth.browser.min.js` | MIT, except lop/option/dingbat-to-unicode (**BSD-2-Clause**), ieee754 (**BSD-3-Clause**) and inherits (**ISC**) | [`licenses/mammothjs-BSD2.txt`](licenses/mammothjs-BSD2.txt) |
| jsPDF, html2canvas, canvg, **DOMPurify 2.3.0**, core-js / core-js-pure, @babel/runtime-corejs3, regenerator-runtime, es6-promise, fflate, omggif, performance-now, raf, rgbcolor, stackblur-canvas, svg-pathdata, **tslib** | `html2pdf.bundle.min.js` | Mostly MIT; **DOMPurify is MPL-2.0 OR Apache-2.0**, **tslib is 0BSD**, and jsPDF contains BSD-3-Clause code from Adobe Systems Incorporated and Dominik Homberger | [`licenses/html2pdf-bundle-LICENSE.txt`](licenses/html2pdf-bundle-LICENSE.txt) |
| [dijkstrajs](https://github.com/tcort/dijkstrajs) | `qrcode.min.js` | MIT (© 2008 Wyatt Baldwin) | [`licenses/node-qrcode-MIT-LICENSE.txt`](licenses/node-qrcode-MIT-LICENSE.txt) |
| Modernizr 3.0.0pre (Custom Build) | `react-dom.production.min.js` | MIT (The Modernizr Team) | [`licenses/react-MIT-LICENSE.txt`](licenses/react-MIT-LICENSE.txt) |

**Two version claims are hedged on purpose.** `html2pdf.bundle.min.js` matches
the published html2pdf.js 0.10.2 bundle byte-for-byte *except* for one string
inside the bundled jsPDF language table, so it is a **rebuild** of ~0.10.2 and
its version cannot be asserted flatly. `qrcode.min.js` is an esbuild bundle of
node-qrcode's browser entry that matches **no** published node-qrcode artifact
at all (1.4.x, 1.5.0-1.5.1 and 1.5.2+ all differ in shape or size), so its
upstream version is unknown. Both arrived with the upstream fork and should be
re-vendored from pinned releases — html2pdf together with its own
`html2pdf.bundle.min.js.LICENSE.txt` sidecar.

*That sidecar is why `licenses/html2pdf-bundle-LICENSE.txt` now exists: the
bundle's first line points at a companion notice file that was never shipped.
The upstream file (143 KB, ~20 copyright holders) is reproduced verbatim.
Previous revisions of this file described the bundle as containing "jsPDF +
html2canvas", which understated it and hid a dual-licensed MPL component.*

---

## Front-end libraries loaded at runtime (CDN)

Fetched from `cdn.jsdelivr.net` on demand — not vendored, not redistributed. The
app's Content-Security-Policy (`core/middleware.py`) permits **only**
`cdn.jsdelivr.net` for scripts, styles and fonts; nothing from any other CDN can
load.

| Library | Loaded by | Purpose | License |
|---|---|---|---|
| [KaTeX](https://github.com/KaTeX/KaTeX) 0.16.22 | `static/index.html` | Math typesetting (incl. its own web fonts) | MIT |
| [Mermaid](https://github.com/mermaid-js/mermaid) 11.x | `static/index.html` | Diagrams from text | MIT |
| [Pyodide](https://github.com/pyodide/pyodide) 0.27.5 | `static/js/codeRunner.js` | In-browser Python runtime | MPL-2.0 (its payload also ships CPython, PSF-2.0) |

**Correction — PDFObject.** An earlier revision of this table credited
[PDFObject](https://github.com/pipwerks/PDFObject) (MIT, pipwerks) as a MyPaiOS
CDN dependency. **MyPaiOS does not load it.** Its only occurrence in the tree is
a string inside the vendored `html2pdf.bundle.min.js`, belonging to jsPDF's
optional PDF-preview output mode, which MyPaiOS does not use — and which the
app's own CSP would block anyway. The row has been removed. (The earlier
preamble also named `cdnjs.cloudflare.com`, which the CSP forbids.)

**Privacy note.** These are the only outbound requests MyPaiOS's UI makes to a
third party. Loading them tells jsDelivr your IP address and when you opened the
app — worth knowing for a local-first tool. For a fully offline install, vendor
KaTeX, Mermaid and Pyodide into `static/lib/` (adding their licence texts to
`licenses/`) and drop `cdn.jsdelivr.net` from the CSP.

---

## Desktop shell

The optional desktop wrapper in `desktop-electron/`:

| Component | Role | License |
|---|---|---|
| [Electron](https://github.com/electron/electron) 33.x | Desktop window + packaging (`desktop-electron/main.js`, `preload.js`) | MIT (© Electron contributors / © 2013-2020 GitHub Inc.) |
| [electron-builder](https://github.com/electron-userland/electron-builder) 25.x | Builds the `.dmg` / `.nsis` / `.AppImage` | MIT |
| Chromium (embedded in Electron) | Renderer | BSD-3-Clause + many third-party licences |
| Node.js / V8 (embedded in Electron) | Main-process runtime | MIT / BSD-3-Clause |

Both are devDependencies installed by npm; **no Electron binaries are committed
to this repository.** But unlike the rest of MyPaiOS, a **packaged desktop app
does redistribute third-party binaries.** Any `.dmg` / `.exe` / `.AppImage` you
publish must include Electron's `LICENSE` and `LICENSES.chromium.html` —
electron-builder copies both into the bundle by default; verify they are present
in `desktop-electron/dist/` before releasing. See
[`licenses/electron-MIT-LICENSE.txt`](licenses/electron-MIT-LICENSE.txt).

(`build-macos-app.sh` and `desktop.py` are the alternative desktop paths; they
are launcher-only — they drive the repo's own venv rather than bundling it.)

---

## Local speech, vision, video & image generation

Runtime dependencies (installed via pip, **not** distributed with this
repository) and model weights (downloaded on demand, **never** bundled):

| Component | Role in MyPaiOS | License |
|---|---|---|
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (SYSTRAN) | Local speech-to-text (`services/stt/`) and video transcripts (`services/video/analyzer.py`); CPU int8 by default | MIT |
| [CTranslate2](https://github.com/OpenNMT/CTranslate2) (SYSTRAN / OpenNMT) | The inference engine faster-whisper runs on | MIT |
| [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) | ONNX wrapper for local TTS (`services/tts/tts_service.py`). **Pulls copyleft dependencies — see the compatibility notes** | MIT (© 2025 github.com/thewh1teagle) |
| [soundfile](https://github.com/bastibe/python-soundfile) | WAV encode/decode on the local-TTS path | BSD-3-Clause (bundles libsndfile, LGPL-2.1-or-later) |
| [Docling](https://github.com/docling-project/docling) (IBM / DS4SD) | **Default** document + OCR engine — PDF/image/Office → Markdown with layout and tables (`src/docling_runtime.py`; also `src/personal_docs.py`, `services/storage.py`, `routes/models_hub_routes.py`). Set `PAIOS_PDF_ENGINE=pypdf` to bypass | MIT |
| [RapidOCR](https://github.com/RapidAI/RapidOCR) (RapidAI) | The OCR step inside Docling's scanned-PDF path | Apache-2.0 (its PP-OCR models derive from PaddleOCR, Apache-2.0) |
| [OpenCV](https://github.com/opencv/opencv-python) (`opencv-python`) | Keyframe extraction / scene-change detection (`services/video/analyzer.py`). **Declared in no requirements file** — currently present only because Docling → RapidOCR pulls it; `pip install opencv-python` explicitly if you use video analysis without Docling | Apache-2.0. The non-headless wheels bundle prebuilt FFmpeg (LGPL-2.1-or-later) and other libraries; `opencv-python-headless` omits them. MyPaiOS distributes neither |
| [PyAV](https://github.com/PyAV-Org/PyAV) (`av`) | **Transitive only** — installed with faster-whisper, which uses it internally to decode audio | BSD-3-Clause. The PyPI `av` wheels bundle prebuilt FFmpeg shared libraries (LGPL-2.1-or-later, no GPL components) |
| [mflux](https://github.com/filipstrand/mflux) (Filip Strand) | The local image-generation engine — runs Z-Image-Turbo and FLUX.1-schnell on Apple Silicon (`scripts/flux_server.py`, exposed as an OpenAI-compatible `/v1/images/generations`) | MIT |
| [MLX](https://github.com/ml-explore/mlx) + `mlx-metal` (Apple) | Apple-Silicon array / NN framework that mflux runs on | MIT (© 2023 Apple Inc.) |
| [diffusers](https://github.com/huggingface/diffusers) (Hugging Face) | Diffusion serving path (`scripts/diffusion_server.py`; registry in `services/hwfit/image_models.py`). **Imported but declared in no requirements file** | Apache-2.0 |
| [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) (Xintao Wang) | Local image upscale + denoise (`routes/gallery_routes.py`) | BSD-3-Clause |
| [BasicSR](https://github.com/XPixelGroup/BasicSR) | RRDBNet architecture used by the Real-ESRGAN path | Apache-2.0 |
| [rembg](https://github.com/danielgatis/rembg) | Background removal (`routes/gallery_routes.py`) | MIT |
| **[GFPGAN](https://github.com/TencentARC/GFPGAN)** (Tencent ARC) *(optional — face enhancement only)* | AI face restoration (`/api/image/enhance-face`) | **Apache-2.0, but with non-commercial third-party components — see the compatibility notes** |

**Correction — PyAV.** Earlier revisions of this file and of `NOTICE` credited
PyAV for "audio-track demux for video analysis (`services/video/analyzer.py`)".
**Nothing in this repository imports `av`.** The analyzer probes metadata by
running `ffprobe` as a subprocess and extracts keyframes with `cv2`;
transcripts come from `services/stt/`. PyAV is present purely as a
faster-whisper transitive dependency. The docstring in
`services/video/analyzer.py` that claimed otherwise is likewise inaccurate.
Its role has been re-scoped above.

---

## AI model weights (downloaded at runtime, never bundled)

**MyPaiOS ships no model weights.** It downloads or recommends them on your
behalf, into your own cache. **Model licences are separate from this
repository's MIT licence and compliance is the operator's responsibility** —
especially for commercial use. The catalogs that surface these
(`services/local_ai/popular.json`, `services/local_ai/catalog.json`,
`services/hwfit/image_models.py`, `services/hwfit/data/hf_models.json`) record
no licence field, so this table is the only licensing signal the project gives.
Read the model card before you rely on anything here.

### The shipped default generalist is not permissively licensed

MyPaiOS's default local generalist is **`hermes3:8b`**
([Hermes 3](https://huggingface.co/NousResearch/Hermes-3-Llama-3.1-8B), Nous
Research) — agents created in the Agents hub are pinned to it
(`routes/agents_hub_routes.py`), Crew planning routes to it
(`services/crew/router.py`), the Telegram gateway runs on it, and Mail Guard
batches through it. Its weights are under the **Llama 3 Community License** (the
model card's licence tag is literally `llama3`); it is a Llama-3.1 fine-tune,
not an OSI-permissive model. Meta's licence carries attribution/naming terms, an
Acceptable Use Policy and a >700M-MAU commercial carve-out. If your deployment
is commercial, read them — or swap in `qwen3` or `gpt-oss` (both Apache-2.0) for
a fully permissive stack.

### Non-permissive / restricted model weights offered by the Cookbook

| Model | Publisher | Weights license | Watch out |
|---|---|---|---|
| `command-r`, `command-r-plus` | Cohere Labs | **CC-BY-NC-4.0** | **Non-commercial only**, plus an Acceptable Use Policy |
| `codestral` | Mistral AI | **MNPL-0.1** (Mistral AI Non-Production License) | **Non-commercial / non-production only** |
| `starcoder2` | BigCode | **BigCode OpenRAIL-M v1** | Use restrictions; generated code may carry its own terms |
| `gemma2`, `gemma3`, `codegemma` | Google | **Gemma Terms of Use** | Hugging Face-gated; Prohibited Use Policy; terms must be passed downstream |
| `minicpm-v` | OpenBMB | **MiniCPM Model License** | Commercial use free **after registration** |
| `deepseek-coder-v2` | DeepSeek | **DeepSeek Model License** | Commercial OK, custom use restrictions |
| `codellama` | Meta | **Llama 2 Community License** | Not OSI-open |
| `hermes3`, `llama3.1`, `llama3.2`, `llama3.3`, `dolphin3` | Meta / Nous Research / Cognitive Computations | **Llama 3.x Community License** | Naming + acceptable-use terms; MAU carve-out |
| `llama3.2-vision` | Meta | **Llama 3.2 Community License** | **Multimodal use is not licensed for EU-domiciled individuals/entities** |
| `qwen2.5:3b`, `qwen2.5-coder:3b`, `qwen2.5vl:3b` | Alibaba Qwen | **Qwen-Research** | **Research-only — the other sizes of the same models are Apache-2.0.** A genuine size-specific trap |
| `qwen2.5:72b`, `qwen2.5vl:72b` | Alibaba Qwen | **Qwen License** (custom) | Not Apache-2.0 |
| `black-forest-labs/FLUX.1-dev`, `FLUX.2-dev` | Black Forest Labs | **FLUX.1/2 [dev] Non-Commercial License** | **Non-commercial only**; HF-gated. Use `FLUX.1-schnell` (Apache-2.0) for commercial work |
| `stabilityai/stable-diffusion-3.5-{medium,large,large-turbo}`, `stable-diffusion-3-medium-diffusers` | Stability AI | **Stability AI Community License** | Free below **US$1M annual revenue**; above that a paid Stability licence + registration is required |
| `stabilityai/stable-diffusion-xl-base-1.0`, SDXL / SD1.5 inpainting | Stability AI / RunwayML | **CreativeML Open RAIL(++)-M** | Enumerated **use restrictions** that must be passed to downstream users; not OSI-approved |
| `tencent/HunyuanImage-3.0`, `-Instruct-Distil` | Tencent | **Tencent Hunyuan Community License** | Not OSI-approved; **territorial restrictions** (reported to exclude the EU, UK and South Korea) and a MAU carve-out |
| [LTX-Video](https://huggingface.co/Lightricks/LTX-Video) | Lightricks | **LTX-Video Open Weights License** (custom) | Not OSI-permissive — read the licence file. Registered as a served endpoint; MyPaiOS never downloads it |

### Permissively-licensed weights

| Model | Role | License |
|---|---|---|
| [Tongyi-MAI/Z-Image-Turbo](https://huggingface.co/Tongyi-MAI/Z-Image-Turbo), Z-Image | **Default** local image model, served via mflux; ungated | Apache-2.0 |
| [Qwen/Qwen-Image](https://huggingface.co/Qwen/Qwen-Image), Qwen-Image-2512, Qwen-Image-Edit-2511 | Cookbook image models | Apache-2.0 *(as asserted by the in-tree catalog descriptions — verify each model card, since Qwen licensing is model- and size-specific)* |
| [black-forest-labs/FLUX.1-schnell](https://huggingface.co/black-forest-labs/FLUX.1-schnell) | Optional local image model (`FLUX_FAMILY=flux`) | Apache-2.0 — **but the Hugging Face repo is gated**: you must accept BFL's conditions and share contact information before download |
| [hexgrad/Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) | The TTS model. `scripts/download_kokoro.py` fetches the ONNX build and voicepack (`kokoro-v1.0.onnx`, `voices-v1.0.bin`) redistributed by the [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) GitHub releases | Apache-2.0 (weights) / MIT (wrapper) |
| OpenAI **Whisper** — fetched as **SYSTRAN's CTranslate2 conversions** (`Systran/faster-whisper-{tiny,base,small,large-v3}`) by faster-whisper on first use; default size `base` | Local STT and video transcripts | MIT (both OpenAI's original research/checkpoints and SYSTRAN's conversions) |
| [ds4sd/docling-models](https://huggingface.co/ds4sd/docling-models) (IBM Deep Search Team) | Layout + TableFormer weights Docling fetches on first conversion; prefetched by the Local AI hub | **CDLA-Permissive-2.0** (the repo also tags Apache-2.0; the card does not disambiguate which applies to which artifact) |
| [RapidOCR](https://github.com/RapidAI/RapidOCR) PP-OCR ONNX models | OCR for scanned PDFs via Docling | Apache-2.0 (derived from PaddleOCR, Apache-2.0) |
| [all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) (Sentence-Transformers / UKP Lab) | **Default** embedding model for RAG, semantic memory and tool selection (`routes/embedding_routes.py`, `src/embeddings.py`) | Apache-2.0 |
| [BAAI/bge-small\|base\|large-en-v1.5](https://huggingface.co/BAAI) | Alternative embedding models offered in Settings | MIT |
| [nomic-ai/nomic-embed-text-v1.5](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5) | Alternative embedding model | Apache-2.0 |
| `gpt-oss` (OpenAI), `qwen3` / `qwen3-coder` / `qwen3-vl` / non-3B-non-72B `qwen2.5*`, `mistral`, `mixtral`, `mistral-small:24b`, `devstral`, `granite-code`, `granite3.3`, `smollm2`, `tinyllama`, `moondream`, `nomic-embed-text`, `mxbai-embed-large` | Ollama catalog | Apache-2.0 |
| `phi4`, `phi3.5` (Microsoft); `deepseek-r1` (DeepSeek's contribution) | Ollama catalog | MIT |

### Where the catalogs come from

- **`services/local_ai/popular.json`** — the curated Ollama list is
  **hand-written MyPaiOS text**: the one-line blurbs are our own, not copied
  from ollama.com or any other catalog (spot-checked against Ollama's library
  pages, which use full publisher sentences where ours use 3-8 word
  MyPaiOS-voice fragments). What *is* derived from ollama.com/library is the
  factual model-name-and-tag curation. `services/local_ai/discover.py` reads
  sizes from the public Ollama registry API (`registry.ollama.ai/v2`) before any
  download.
- **`services/hwfit/data/hf_models.json`** — 911 entries combining the **llmfit**
  base catalog (MIT, Alex Jones — credited above) with **factual model metadata
  fetched from the public [Hugging Face Hub](https://huggingface.co) API**
  (`huggingface_hub`, Apache-2.0) by `scripts/add_hwfit_models.py`; 705 rows are
  flagged `_discovered`. Hugging Face is a trademark of Hugging Face, Inc.;
  MyPaiOS is not affiliated with or endorsed by it. **The catalog records no
  licence information** — every model you download through the Cookbook is
  governed by its own weights licence on its model card.
- The **image-model registry** (`services/hwfit/image_models.py`) also lists
  third-party FP8 quantizations (`drbaph/Z-Image-Turbo-FP8`,
  `drbaph/Z-Image-fp8`) — derivatives whose own licence tags should be checked
  before commercial use.

---

## Packages the Cookbook installs on your behalf

The Cookbook → Dependencies panel can `pip install` the packages below into your
own environment (allowlist in `routes/shell_routes.py`). MyPaiOS distributes
none of them — you are installing them from PyPI under their own licences. Two
carry terms a commercial user needs to know about **before** clicking the button.

| Package | Purpose | License |
|---|---|---|
| rembg | Background removal (image editor) | MIT (u2net weights: Apache-2.0) |
| realesrgan + basicsr | Denoise / upscale | BSD-3-Clause / Apache-2.0 |
| gfpgan | Face restoration | Apache-2.0 (Tencent ARC) — **but see below** |
| diffusers\[torch] | Image-generation pipelines | Apache-2.0 |
| llama-cpp-python\[server] | GGUF serving | MIT |
| vllm, sglang\[all] | LLM serving | Apache-2.0 |
| bark | Generative audio | MIT |
| faster-whisper | STT | MIT |
| playwright | Browser automation | Apache-2.0 |
| onnxruntime / onnxruntime-gpu | ONNX inference | MIT |
| hf_transfer | Fast Hugging Face downloads | Apache-2.0 |
| hdbscan | Clustering | BSD-3-Clause |
| **TTS** (Coqui) | Alternative TTS engine | **MPL-2.0** — and its pretrained models (e.g. XTTS) are released under the separate, non-OSI **Coqui Public Model License**. Check it before commercial use |
| **insightface** | Face analysis | Code **MIT**, but the **pretrained models are licensed for non-commercial research purposes only**, and several model series (inswapper, buffalo_l, InspireFace) require licensing directly from InsightFace. **Do not enable this in a commercial deployment without your own licence** |

---

## Python dependencies

Direct dependencies declared in `requirements.txt` (core) and
`requirements-optional.txt` (optional). **MyPaiOS is distributed as source and
imports these from your own Python environment — it redistributes none of their
code, so permissive (MIT / BSD / ISC / Apache-2.0 / PSF) dependencies impose no
notice obligation on this repository.** These tables exist for transparency and
to isolate the handful of copyleft and non-OSI items, which are called out
explicitly. Packages MyPaiOS imports but does not declare are listed separately
below — an earlier revision of this section claimed to enumerate the two
requirements files while omitting two of their entries and listing three
packages that are in neither.

### Declared

| Package | License |
|---|---|
| FastAPI | MIT |
| Uvicorn | BSD-3-Clause |
| python-multipart | Apache-2.0 |
| python-dotenv | BSD-3-Clause |
| HTTPX | BSD-3-Clause |
| Pydantic / pydantic-settings | MIT |
| SQLAlchemy | MIT |
| pypdf | BSD-3-Clause |
| BeautifulSoup4 | MIT |
| charset-normalizer | MIT |
| NumPy | BSD-3-Clause |
| nh3 | MIT (bindings to the Rust `ammonia` crate, MIT/Apache-2.0) |
| python-dateutil | Apache-2.0 OR BSD-3-Clause (dual) |
| ChromaDB — declared as `chromadb-client` (the lightweight HTTP client); note the reference `requirements.lock.txt` pins the **full `chromadb`** server package, which additionally pulls kubernetes, grpcio, the OpenTelemetry SDK and PyPika (Apache-2.0), mmh3 (MIT) and orjson (MPL-2.0 AND (Apache-2.0 OR MIT)) | Apache-2.0 |
| fastembed | Apache-2.0 — note the PyPI wheel metadata is mislabelled with an `Other/Proprietary License` classifier; the upstream repository (qdrant/fastembed) is Apache-2.0 |
| youtube-transcript-api | MIT |
| markdown | BSD-3-Clause |
| icalendar | BSD-2-Clause |
| **caldav** | GPL-3.0-or-later OR Apache-2.0 (dual; MyPaiOS uses it under Apache-2.0) — **but it hard-requires copyleft packages, see the compatibility notes** |
| ↳ icalendar-searcher *(transitive, required by `caldav/search.py`)* | **AGPL-3.0-or-later** |
| ↳ recurring-ical-events, x-wr-timezone *(transitive, required by caldav)* | **LGPL-3.0-or-later** (© Nicco Kunzmann) |
| cryptography | Apache-2.0 / BSD-3-Clause |
| bcrypt | Apache-2.0 |
| MCP (Model Context Protocol SDK) | MIT |
| pyotp | MIT |
| qrcode\[pil] | BSD-3-Clause |
| ↳ Pillow *(installed by the `pil` extra; also imported directly for all image handling)* | MIT-CMU (HPND-style) |
| croniter | MIT |
| pytest / pytest-asyncio | MIT / Apache-2.0 |
| faster-whisper *(optional — local STT)* | MIT |
| duckduckgo-search *(optional)* | MIT |
| markitdown *(optional — Office/EPUB text extraction)* | MIT (Microsoft) |
| **PyMuPDF** *(optional — form-filling only)* | **AGPL-3.0** — see the compatibility notes |

### Imported but not declared

These are imported by first-party code yet appear in no requirements file. All
are permissive; the point is that the tables above cannot be read as a complete
picture of what runs.

| Package | Where used | License |
|---|---|---|
| **docling** (+ docling-core, -ibm-models, -parse, -slim) | **Default** PDF/OCR engine, `src/docling_runtime.py` and five other sites. Also the reason torch, transformers, rapidocr, opencv-python, pandas and matplotlib are in the environment at all | MIT (IBM / DS4SD) |
| **playwright** | Agentic browser tool (`services/browser/tool.py`; `browser_navigate`/`read`/`click`/`fill`/`screenshot`), plus `app.py` and `routes/shell_routes.py` | Apache-2.0 (Microsoft). The browser binaries it downloads are separate: Chromium (BSD-3-Clause + third-party notices), Firefox (MPL-2.0), WebKit (BSD / LGPL-2.1) |
| **kokoro-onnx**, **soundfile** | Local TTS (`services/tts/tts_service.py`) — the only install hint is a log line in that file | MIT / BSD-3-Clause |
| ↳ **phonemizer-fork** *(required by kokoro-onnx)* | Grapheme→phoneme frontend | **GPL-3.0-or-later** |
| ↳ **espeakng-loader** *(required by kokoro-onnx)* | Loads libespeak-ng | MIT wrapper whose wheel **bundles a compiled libespeak-ng (GPL-3.0-or-later)** + voice data |
| **opencv-python** | Video keyframes (`services/video/analyzer.py`) | Apache-2.0 |
| **diffusers** | `scripts/diffusion_server.py` | Apache-2.0 |
| **mflux**, **mlx**, **mlx-metal** | `scripts/flux_server.py` local image server | MIT / MIT (Apple) |
| torch, torchvision | Optional GPU paths, TTS/diffusion servers | BSD-3-Clause |
| transformers, huggingface_hub, hf_transfer, accelerate, safetensors, sentencepiece | Embeddings + model downloads | Apache-2.0 |
| onnxruntime | ONNX inference (fastembed, Kokoro, magika) | MIT |
| ctranslate2 | faster-whisper backend | MIT (SYSTRAN) |
| rapidocr | OCR inside Docling | Apache-2.0 |
| pywebview (`webview`) | `desktop.py` native window | BSD-3-Clause |
| python-magic (`magic`) | MIME sniffing (`src/upload_handler.py`, guarded) | MIT (wraps libmagic, BSD-2-Clause) |
| pdfminer.six | PDF text from crawled URLs (`services/search/content.py`, guarded) | MIT |
| python-docx, python-pptx | Office extraction (`src/personal_docs.py`, `src/upload_handler.py`) | MIT |
| magika | File typing (via markitdown) | Apache-2.0 (Google) |
| requests | Alongside the declared httpx | Apache-2.0 |
| psutil, PyYAML, lxml, starlette | Assorted | BSD-3-Clause / MIT / BSD-3-Clause / BSD-3-Clause |
| defusedxml | XML hardening | PSF-2.0 |
| tqdm | Progress bars | **MPL-2.0 AND MIT** |

`requirements.lock.txt` freezes the **core** set only — it does not cover
`requirements-optional.txt`, so `markitdown` and the other pinned optional
extras (and their transitive sets) are not captured there. It also includes the
maintainer's release tooling (twine, build, readme_renderer, docutils, Faker,
keyring), which is **not** part of any user's runtime; `docutils` in particular
carries mixed Public-Domain / BSD / **GPL** classifiers and is dev-only, never
imported by MyPaiOS.

## npm dependencies

Declared in the root `package.json` / `package-lock.json`. Installed via npm —
`node_modules/` is **not** distributed with this repository.

| Package | Role | License |
|---|---|---|
| [@anthropic-ai/sdk](https://github.com/anthropics/anthropic-sdk-typescript) 0.98.x | Anthropic API client. **Nothing in the tree imports it** — it looks like dead weight and is a candidate for removal rather than for credit | MIT |
| [@antithesishq/bombadil](https://www.npmjs.com/package/@antithesishq/bombadil) 0.3.x *(dev)* | Test harness | MIT |
| json-schema-to-ts, ts-algebra, @babel/runtime, standardwebhooks, @stablelib/base64 *(transitive)* | Type utilities, webhook signature verification | MIT |
| fast-sha256 *(transitive)* | SHA-256 | **Unlicense** (public-domain dedication) |

See also [Desktop shell](#desktop-shell) for `desktop-electron/package.json`.

---

## Container images and base image

MyPaiOS's own image is built from the
[`python:3.12-slim`](https://hub.docker.com/_/python) Docker Official Image
(CPython under **PSF-2.0** on a Debian *bookworm* slim base). The `Dockerfile`
additionally apt-installs, from Debian's own repositories:

| Package | Why | License |
|---|---|---|
| gosu | entrypoint drops privileges to PUID/PGID | Apache-2.0 |
| tmux | Cookbook background downloads / serves | ISC |
| openssh-client | Cookbook remote model servers | BSD-style permissive |
| git | Cookbook builds llama.cpp on first launch | GPL-2.0 |
| build-essential (GCC), cmake | same | GPL-3.0 w/ GCC Runtime Library Exception; BSD-3-Clause |
| nodejs, npm | `npx` for the optional Browser MCP server | MIT; Artistic-2.0 |
| curl | health / probe helpers | curl licence (MIT-style) |

**This repository distributes a `Dockerfile`, not an image** — none of those
binaries are redistributed here, so no third-party notices travel with the repo.
If a prebuilt MyPaiOS image is ever published, see
[Before publishing a binary artifact](#before-publishing-a-binary-artifact).

The sidecar services below are pulled as images by `docker-compose.yml` and run
alongside MyPaiOS. They are not modified and not redistributed — just composed.
(**Ollama, Radicale and Dovecot are *not* in any compose file**; see
[System binaries and companion services](#system-binaries-and-companion-services).)

| Service | Image | Purpose | License |
|---|---|---|---|
| [SearXNG](https://github.com/searxng/searxng) | `searxng/searxng:2026.5.31-7159b8aed` (pinned; see compose) | Default metasearch backend | AGPL-3.0 |
| [ChromaDB](https://github.com/chroma-core/chroma) | `chromadb/chroma:latest` *(unpinned — worth pinning)* | Vector store for memory / RAG | Apache-2.0 |
| [ntfy](https://github.com/binwiederhier/ntfy) | `binwiederhier/ntfy` *(untagged → `:latest`; worth pinning)* | Push notifications | Apache-2.0 OR GPL-2.0 (dual; run as an unmodified image, so no election is required — MyPaiOS does not redistribute it) |

`config/searxng/settings.yml` is nine lines of original MyPaiOS configuration
(`use_default_settings: true` plus a secret placeholder and formats), not a copy
of upstream's AGPL settings template.

### CI tooling (not distributed)

GitHub Actions used by `.github/workflows/` — `actions/checkout`,
`actions/setup-python`, `actions/setup-node`, `actions/github-script` (all MIT,
© GitHub, Inc.) — execute on GitHub's runners and are never copied into or
distributed with this repository, so they carry no notice obligation. Listed
only for supply-chain transparency.

---

## System binaries and companion services

MyPaiOS talks to these over the network, or **shells out to them as separate
processes**. They are **not** distributed with this project and it links against
none of them; their licences do not bind this codebase, but they deserve credit:

- [Ollama](https://github.com/ollama/ollama) — local model serving (MIT)
- [llama.cpp](https://github.com/ggml-org/llama.cpp) — GGUF serving; the
  Cookbook clones and builds `llama-server` from upstream source on your own
  machine (`routes/cookbook_routes.py`) or uses a Homebrew build
  (`start-macos.sh`), and computes serve profiles against its flags
  (`services/hwfit/profiles.py`). Never vendored here (MIT)
- [vLLM](https://github.com/vllm-project/vllm) and
  [SGLang](https://github.com/sgl-project/sglang) — GPU serving backends the
  Cookbook generates launch commands for (Apache-2.0)
- [Radicale](https://github.com/Kozea/Radicale) — CardDAV/CalDAV server (GPL-3.0)
- [Dovecot](https://www.dovecot.org/) — IMAP server (MIT / LGPL-2.1)
- [isync / mbsync](https://isync.sourceforge.io/) — IMAP mailbox sync (GPL-2.0)
- [tmux](https://github.com/tmux/tmux) — terminal multiplexer; Cookbook shells
  out to it for background model downloads and serves (ISC)
- [OpenSSH](https://www.openssh.com/) (`ssh`, `ssh-keygen`, `ssh-copy-id`) —
  Cookbook shells out to it to manage remote model servers (BSD-style permissive)
- [ffmpeg / ffprobe](https://ffmpeg.org/) — video metadata probing. MyPaiOS
  **invokes `ffprobe` as a separate process** (`subprocess`,
  `services/video/analyzer.py`); it contains no FFmpeg source, headers or
  binaries, links against no FFmpeg library, and distributes nothing from the
  FFmpeg project. **You install it yourself** and it stays under its own licence
  — LGPL-2.1-or-later, or GPL-2.0-or-later if your build includes GPL-only
  components. Note separately that prebuilt FFmpeg *libraries* do reach your
  environment inside the PyPI wheels for `av` and `opencv-python`; those are
  LGPL-2.1 builds, installed by you, not distributed here
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — YouTube comment fetching
  (`services/youtube/youtube_handler.py`); shelled out to, never bundled (The
  Unlicense / public domain). Automated downloading may conflict with YouTube's
  Terms of Service; transcripts use the `youtube-transcript-api` path by default
- [@playwright/mcp](https://github.com/microsoft/playwright-mcp) (Microsoft) —
  the optional built-in Browser MCP server, fetched on demand with
  `npx -y @playwright/mcp@latest` (`src/builtin_mcp.py`); the Dockerfile installs
  nodejs/npm specifically to provide `npx` for it. Apache-2.0. It and the browser
  engines Playwright downloads (Chromium — BSD-3-Clause plus third-party
  notices; Firefox — MPL-2.0; WebKit — BSD / LGPL-2.1) land in your own
  npm/Playwright caches and are not distributed with MyPaiOS. *(The `@latest`
  tag is unpinned.)*
- Anthropic **Claude Code** (`claude`), OpenAI **Codex CLI** (`codex`) and
  Google **Gemini CLI** (`gemini`) — shelled out to by
  `routes/cli_llm_routes.py` for the `claude-cli` / `codex-cli` / `gemini-cli`
  models, so your own subscription answers the chat. Claude Code is proprietary;
  Codex CLI and Gemini CLI are Apache-2.0 *(asserted from the upstream projects,
  not re-verified here)*. MyPaiOS never sees or stores credentials for them —
  each CLI keeps its own login. **Using a personal subscription as a backend for
  another application is governed by that vendor's terms**; check yours.

## External services and APIs (your keys, your accounts)

MyPaiOS talks to these over the network when you configure them. It bundles none
of their code. An earlier revision of this file listed only four providers
("Anthropic, OpenAI, Google (Gemini), DuckDuckGo"), which the code contradicts.

**Model / inference APIs** — OpenAI, Anthropic, Google (Gemini), OpenRouter,
Groq, xAI, Mistral AI, DeepSeek, Together AI, Fireworks AI, Z.AI (GLM), Venice
AI, Perplexity (pricing data only), Ollama Cloud, GitHub Copilot.
**Search** — SearXNG (self-hosted, the default primary), DuckDuckGo, Brave
Search, Google Programmable Search, Tavily, Serper.
**Mail / calendar / contacts** — Microsoft 365 via Microsoft Graph
(`src/ms_graph.py`), IMAP/SMTP servers, CalDAV/CardDAV servers (Radicale,
Nextcloud, Apple iCloud, Fastmail).
**Messaging & notifications** — Telegram Bot API
(`services/gateway/telegram_gateway.py`), ntfy.
**Self-hosted app integrations** (`src/integrations.py`) — Miniflux, Gitea,
Linkding, Home Assistant, Vaultwarden, FreshRSS.
**Knowledge** — Obsidian (your local vault, `src/obsidian_brain.py`), Hugging
Face Hub, the Ollama registry, YouTube.

Using any of them is subject to **that provider's own terms of service** and to
whatever you agreed when you created the account or key. MyPaiOS stores your
keys locally, encrypted, and sends them only to the provider they belong to.

Three specifics worth stating rather than burying:

- **OpenRouter attribution.** When you use an OpenRouter endpoint, MyPaiOS sends
  the attribution headers OpenRouter asks integrators to send —
  `HTTP-Referer: https://github.com/mypaios/mypaios` and `X-Title: MyPaiOS`
  (plus the legacy `X-OpenRouter-Title`). See `src/llm_core.py` and
  `src/endpoint_resolver.py`. They identify the app to OpenRouter for its public
  app rankings and your own per-app analytics, and carry no user content. Please
  keep them if you fork — and change the values to your own project.
- **GitHub Copilot.** GitHub, GitHub Copilot and Visual Studio Code are
  trademarks of GitHub, Inc. / Microsoft Corporation; MyPaiOS is affiliated with
  neither. The Copilot provider authenticates through GitHub's OAuth **device
  flow** and, like other third-party Copilot clients, **reuses the public Visual
  Studio Code OAuth client id** and identifies with the `vscode-chat`
  integration id (`src/copilot.py`), because GitHub only allow-lists client ids
  it has approved for Copilot. Override with `PAIOS_COPILOT_CLIENT_ID` /
  `PAIOS_COPILOT_INTEGRATION_ID` / `PAIOS_COPILOT_USER_AGENT` if you register
  your own allow-listed app. **Using your Copilot subscription through a
  third-party client is subject to your agreement with GitHub** — check it, and
  disable the provider if your terms do not permit it.
- **DuckDuckGo.** The provider prefers the `duckduckgo-search` library (MIT,
  optional, credited above). If that library is absent or fails,
  `services/search/providers.py` falls back to fetching DuckDuckGo's HTML
  results endpoint directly with a browser `User-Agent` — and DuckDuckGo is the
  default search **fallback** (`services/search/core.py`). **Automated access
  may conflict with DuckDuckGo's Terms of Service.** For anything beyond
  personal use, run your own SearXNG instance or use a keyed API (Brave, Tavily,
  Serper, Google PSE).

---

## License-compatibility notes (for the repo's own LICENSE choice)

**The headline, corrected.** An earlier revision of this file said "the core
ships fully permissive (MIT-compatible), so the two copyleft concerns from
earlier are resolved." **That was not accurate.** Copyleft packages *do* reach
the runtime environment, one of them straight from core `requirements.txt`.

What saves the MIT licence is the **distribution shape**, not the dependency
set: **this repository contains no copyleft code.** `.gitignore` excludes
`venv/`, `data/` and `node_modules/`; `build-macos-app.sh` and
`desktop-electron/main.js` are launcher-only (they drive your own repo venv
rather than bundling it); and no GitHub workflow builds or publishes an image.
Every AGPL/LGPL/GPL obligation below attaches to a **built artifact**, not to
the source tree — so MyPaiOS-under-MIT is sound today, and stays sound as long
as nobody ships a binary without reading the next section.

- **PDF text extraction** uses **Docling** (MIT, IBM) **by default**, falling
  back to **`pypdf`** (BSD-3-Clause) when Docling is absent or a conversion
  fails; set `PAIOS_PDF_ENGINE=pypdf` to force the fallback. Both engines are
  permissive. **Encoding detection** uses **`charset-normalizer`** (MIT);
  chardet (LGPL-2.1) has been removed entirely. *(An earlier revision said
  extraction "now uses pypdf", which was misleading once Docling became the
  default.)*
- **`caldav` is not the permissive story it reads as.** The library itself is
  dual-licensed **GPL-3.0-or-later OR Apache-2.0** and MyPaiOS uses it under
  Apache-2.0 — but `pip install caldav` also installs **`icalendar-searcher`
  (AGPL-3.0-or-later)**, which `caldav/search.py` hard-imports, plus
  **`recurring-ical-events`** and **`x-wr-timezone`** (both
  **LGPL-3.0-or-later**). `caldav` is in core `requirements.txt`. No copyleft
  code is *in* this repository — these are installed by you from PyPI — but a
  redistributed artifact containing them carries their obligations, including
  AGPL §13's requirement to offer Corresponding Source to users interacting with
  it over a network. For a fully permissive CalDAV-free install, omit `caldav`;
  the rest of MyPaiOS runs unaffected.
- **Local TTS is a copyleft path.** `pip install kokoro-onnx` pulls
  **`phonemizer-fork` (GPL-3.0-or-later)** and **`espeakng-loader`**, whose
  wheel **bundles a compiled `libespeak-ng` (GPL-3.0-or-later)** plus voice
  data. So espeak-ng is *not* merely a system binary here: pip places GPL-3.0
  binaries in your `site-packages` whether or not you ever run
  `brew install espeak-ng` (which the code's install hint implies you must).
  `soundfile` likewise bundles `libsndfile` (LGPL-2.1-or-later). MyPaiOS ships
  none of this and links against none of it; the MIT core runs with local TTS
  disabled (any HTTP TTS endpoint, or no TTS).
- **PyMuPDF (AGPL-3.0)** is not a core dependency. It is **optional** and used
  *only* by the PDF form-filling feature (`src/pdf_forms.py`,
  `src/pdf_runtime.py`, and the form endpoints in `routes/document_routes.py`),
  lazy-imported and listed in `requirements-optional.txt`; the Dockerfile gates
  it behind `ARG INSTALL_OPTIONAL=false`. The MIT core runs without it. If you
  install it, AGPL's network clause applies to *that feature* for your
  deployment (Artifex also sells a commercial licence that lifts this). **This
  is the pattern the caldav and kokoro paths above should be held to.**
- **GFPGAN carries non-commercial components.** It is **optional** and used
  *only* by `/api/image/enhance-face` (`routes/gallery_routes.py`),
  lazy-imported behind a `try/except ImportError` that falls back to a pure-PIL
  enhancement path — the MIT core runs, and that endpoint still works, without
  it. GFPGAN is Apache-2.0, **but its own LICENSE carves out third-party code it
  incorporates**: StyleGAN2 under the **NVIDIA Source Code License
  (non-commercial only)** and DFDNet under **CC BY-NC-SA 4.0**. If you install
  GFPGAN, those non-commercial terms apply to that feature in your deployment.
  **Commercial deployments should leave GFPGAN uninstalled**; the PIL fallback
  and the BSD-3-Clause Real-ESRGAN paths are unaffected.
- **Weak copyleft in the default install.** `certifi` (MPL-2.0), `tqdm`
  (MPL-2.0 AND MIT) and `orjson` (MPL-2.0 AND (Apache-2.0 OR MIT)) arrive
  transitively. MPL-2.0 is *file-level* copyleft and explicitly permits
  combination with a larger MIT work, so it does not affect MyPaiOS's own
  licence. MyPaiOS ships no MPL-covered files and modifies none; a published
  container image or frozen bundle containing them must make those files' Source
  Code Form available under MPL §3.2 (pointing at the upstream project
  satisfies this).
- **`markitdown`** (Microsoft) is **MIT** and used only as an *optional*,
  lazy-imported converter for Office/EPUB text extraction
  (`src/markitdown_runtime.py`) with graceful fallback; the cloud
  `az-doc-intel` extra is deliberately **not** installed, keeping extraction
  fully local. It is complementary to Docling, which handles PDFs and images
  including OCR. Note that `requirements.lock.txt` covers only
  `requirements.txt`, so markitdown's transitive set is not pinned there — and
  an earlier revision of this note asserted a specific transitive list
  (mammoth / xlrd / magika …) that is not verifiable against the reference
  environment.
- **JSZip** (bundled inside two vendored front-end files) is dual-licensed
  **MIT OR GPL-3.0-or-later**. MyPaiOS uses it under **MIT**; no GPL code is
  distributed by this repository.
- **DOMPurify** (bundled inside `html2pdf.bundle.min.js` by jsPDF) is
  dual-licensed **MPL-2.0 OR Apache-2.0**. MyPaiOS uses it under
  **Apache-2.0**, unmodified, so no MPL source-disclosure obligation attaches.
- **SearXNG is AGPL-3.0** but runs as a **separate service** in its own
  container, unmodified, communicating over HTTP. It is not linked into or
  distributed by MyPaiOS.

### Before publishing a binary artifact

MyPaiOS is distributed as **source**, and this repository contains no copyleft
or proprietary third-party code. A *built artifact* is different — it contains
whatever pip and npm put in it. Before publishing one, note that it will
include:

- **AGPL-3.0-or-later**: `icalendar-searcher` (required by `caldav`) — and
  `PyMuPDF` too if you build with `INSTALL_OPTIONAL=true`. AGPL §13 requires you
  to offer Corresponding Source to users who interact with it over a network.
- **LGPL-3.0-or-later**: `recurring-ical-events`, `x-wr-timezone`.
- **GPL-3.0-or-later**: `phonemizer-fork` and the `libespeak-ng` bundled by
  `espeakng-loader`, if local TTS is installed.
- **LGPL-2.1-or-later**: FFmpeg libraries bundled inside the `av` and
  `opencv-python` wheels; `libsndfile` bundled inside `soundfile`.
- **MPL-2.0**: `certifi`, `tqdm`, `orjson`.
- **Proprietary**: on Linux/CUDA builds, the NVIDIA runtime libraries vendored
  inside the `torch` wheel, under NVIDIA's own licence (cuBLAS, cuDNN, NCCL …).
- **Debian GPL userland**: a container image built from `python:3.12-slim` with
  the Dockerfile's apt packages includes GPL-2.0/GPL-3.0 binaries (git, GCC),
  whose source-offer obligations then fall on the publisher.
- **For desktop builds**: Electron, Chromium and Node.js — ship their licence
  notices (see [Desktop shell](#desktop-shell)).

The Dockerfile's own comment ("optional extras are opt-in so the default image
stays MIT-core") is therefore too optimistic: even the default image is not
fully permissive, because `caldav` pulls AGPL-3.0 `icalendar-searcher`.
**No GitHub workflow currently publishes any artifact, so none of these
obligations is live today.**

---

## Known open items

Recorded here rather than left for the next auditor to rediscover. None of these
is fixed by a credit line — they are file changes outside the scope of this
attribution record:

1. ~~`docs/index.html` hot-links a third-party stock photograph.~~ **Resolved.**
   `docs/index.html` was rebuilt from scratch and no longer contains any
   external image hotlinks, fabricated testimonials, or third-party CDN
   references of any kind — verified by grep before publication. Left here so
   the fix is on record rather than silently dropped.
2. **`static/fonts/custom/GohuFont.ttf` should be deleted.** The false
   attribution for it has been removed from this file, `NOTICE` and `licenses/`,
   but the 1.4 KB placeholder itself is still on disk and would appear in the
   Theme panel's Font dropdown as a broken 3-glyph font.
3. **`docs/` inherited demo media (13 remaining files, ~17 MB) should
   eventually be deleted.** The clips are upstream Odysseus recordings showing
   upstream's name, logo and tagline. **Partially resolved**: neither the
   README nor `docs/index.html` links or embeds any of them any more (both now
   use MyPaiOS's own screenshots and an original animated banner), so the
   branding-confusion risk on the visible site is gone. The remaining 13 files
   are unreferenced and sit on disk pending re-recording or deletion.
   `docs/gallery.webm` — which showed a real, identifiable person with a dog
   and a personally-named file ("Maya & Eggy / IMG_7774") with no documented
   likeness release — has been **deleted** (not just unlinked), 2026-07-31,
   before this repo went public.
4. **Two provenance claims in source comments cannot be resolved.**
   `services/video/analyzer.py` attributes its tuning constants to "the
   claude-real-video / video-caption ablation recipes", which could not be
   identified as any licensable project or publication — if the values were
   tuned in-house (as "owned in-tree" in the same comment suggests), the comment
   should say so; the same file's "measured ~+26% caption accuracy" should be
   cited or softened. `services/agent_templates.py` says its 40 templates are
   "distilled from" GPT Store / n8n / Lindy / Dust; n8n's template library is
   source-available under a Sustainable Use License and is **not**
   redistributable, so if any wording came from it, it must be removed rather
   than credited. The templates read as original prose written against MyPaiOS's
   own tool names, which is the likely answer — but the comment should be
   reworded to claim category inspiration rather than derivation.
5. **Smaller accuracy items.** `services/pricing/litellm_snapshot.json`'s
   `_meta` block records no licence, source URL or upstream commit, so the
   snapshot is not independently re-verifiable (the MIT obligation itself is
   met by `licenses/litellm-MIT-LICENSE.txt` and the credit in
   `services/pricing/pricebook.py`). `docling`, `opencv-python`, `kokoro-onnx`,
   `soundfile`, `playwright` and `diffusers` are imported but declared in no
   requirements file. `basicsr` is imported at `routes/gallery_routes.py` but is
   missing from the Cookbook's install allowlist, so that path cannot be
   satisfied through the UI. Two stale brand strings remain in outbound
   User-Agents: `PiAOS-LocalAI` (`services/local_ai/discover.py`) and
   `PAIOS/1.0` (`src/copilot.py`).

---

## Thanks to

### Inherited from Odysseus

The acknowledgments below come from **Odysseus**, the upstream project MyPaiOS
forked, and are reproduced as its authors wrote them. Earlier revisions of this
file presented them as MyPaiOS's own by swapping the project name, which
misattributed another author's creation story and their personal thanks:

> Most of Odysseus's code was written *with* AI models, not just by a human.
> The project would not exist without them — credit where credit is due:
>
> - **gpt-oss-120b** — the legend that kicked this project off.
> - **Qwen3-235B**
> - **DeepSeek V3.1 · DeepSeek V4 Pro · DeepSeek V4 Flash**
> - **Claude** (Anthropic)
> - **Codex** (OpenAI)
> - Friends, for helping me debug.

### From MyPaiOS

- The **Odysseus** authors, for the MIT-licensed foundation this fork builds on.
- The maintainers of every project named in this file, most of whom will never
  know MyPaiOS exists.

*This is a thank-you, not a licence notice. No model weights or model outputs
are redistributed here, and nothing in this section grants or limits any rights.
For the licences of models MyPaiOS runs or recommends, see
[AI model weights](#ai-model-weights-downloaded-at-runtime-never-bundled).*
