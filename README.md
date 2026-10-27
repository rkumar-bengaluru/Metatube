# MetaTube

A Claude Code plugin/skill that turns a **video project folder** or **GitHub repo** into a fully
metadata-populated YouTube upload — automatically.

Point it at the source material used to create your video (scripts, slides, code, README, commit
history), and the skill will:

1. **Analyze** the content to understand what the video teaches.
2. **Generate** an SEO-optimized `*.yaml` sidecar for each video (title, description, tags, privacy).
3. **Upload** via [`ytstudio-cli`](https://github.com/jdwit/ytstudio-cli) using those sidecars — with dry-run
validation before any quota is spent.

Claude reasons over the content; `ytstudio-cli` does the deterministic, resumable upload.
Clean separation, fully auditable.

---

## Why this exists

Uploading an educational series by hand is tedious and error-prone:

- Titles get inconsistent across episodes.
- Descriptions are copy-pasted and weakly keyworded.
- Tags are an afterthought (or missing entirely).
- Quota is burned re-uploading failed batches.

This skill makes metadata generation **content-aware** (it reads what the video is actually about)
and makes uploads **repeatable and resumable**.

---

## How it works

```
┌─────────────────────┐
│ Input               │
│ ├─ project folder   │ scripts, slides, notes, README
│ └─ or GitHub repo   │ code, docs, commit history
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ MetaTube Skill      │
│ (SKILL.md)          │
│                     │
│ 1. read + analyze   │
│ 2. draft metadata   │
│ 3. write *.yaml     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ ytstudio-cli        │
│ videos upload …     │
│                     │
│ dry-run → validate  │
│ --execute → upload  │
└──────────┬──────────┘
           │
           ▼
        YouTube
```

**Design principle:** the skill never talks to the YouTube API directly. It writes sidecars and
shells out to `ytstudio-cli`. This means every upload can be reproduced, reviewed, or re-run
without Claude in the loop.

---

## Prerequisites

| Requirement               | Notes                                                                                                                       |
| ------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| **Node.js / Python**      | Whatever runtime `ytstudio-cli` requires — check its docs.                                                                  |
| **`ytstudio-cli`**        | Installed and on your `PATH`. Verify the exact command syntax against its current docs — CLI flags change between versions. |
| **OAuth 2.0 credentials** | ⚠️ An API key is **not** sufficient for uploads. Run `ytstudio init` once to complete the OAuth flow and store credentials. |
| **Claude Code**           | With plugin support enabled.                                                                                                |
| **Google Cloud project**  | YouTube Data API v3 enabled. Default quota is **10,000 units/day**.                                                         |

> **Quota reality check:** a single `videos.insert` call costs **~1,600 units**, so the default
> quota allows roughly **6 uploads per day**. Request a quota increase from Google if you need
> more, and always dry-run before `--execute`.

---

## Repository structure

```
metatube/
├── .claude-plugin/
│   └── plugin.json                 # plugin manifest
├── skills/
│   └── metatube/
│       ├── SKILL.md                # the skill definition (see below)
│       └── references/
│           ├── yaml-schema.md      # sidecar field reference
│           └── seo-guide.md        # title/description/tag conventions
├── examples/
│   ├── single-video/
│   │   ├── python-intro.mp4
│   │   └── python-intro.yaml
│   └── series/
│       ├── episode-01.mp4
│       ├── episode-01.yaml
│       ├── episode-02.mp4
│       └── episode-02.yaml
├── scripts/
│   └── validate-sidecars.sh        # lint YAML before upload
├── README.md
└── LICENSE
```

---

## Quick start

### 1. Clone and install the skill

```bash
git clone https://github.com/<you>/metatube.git
cd metatube
claude plugin install ./
```

### 2. One-time YouTube auth

```bash
ytstudio init
```

Follow the browser prompt to grant OAuth access to your channel.

### 3. Run the skill

From Claude Code, in your video project directory:

```
> /metatube generate metadata for ./episodes
```

Claude will read the folder, draft a sidecar per video, and show you the YAML **before**
writing anything. Review, edit if needed, then confirm.

### 4. Validate, then upload

```bash
# Dry run — no quota consumed
ytstudio videos upload ./episodes

# For real
ytstudio videos upload ./episodes --execute
```

---

## The skill definition

`skills/metatube/SKILL.md` is the heart of the project. A minimal starting version:

```markdown
---
name: metatube
description: Analyzes a video project folder or GitHub repo and generates SEO-optimized
YouTube metadata YAML sidecars, then uploads via ytstudio-cli.
allowed-tools:
  - Bash(ytstudio *)
  - Bash(git *)
  - Read
  - Write
  - Glob
  - Grep
---

# MetaTube

## When to use this skill

Use when the user asks to generate YouTube metadata or upload videos, and provides either:
- a folder containing video files and/or their source material, or
- a GitHub repository that was used to create the video(s).

## Workflow

### 1. Discover videos

Glob the target for `*.mp4`, `*.mov`, `*.mkv`. If none are found, ask the user where the
rendered files are — do not guess.

### 2. Understand the content

For each video, gather context from the same directory and its parents:
- Any `*.md`, `*.txt`, `*.srt`/`*.vtt` transcripts, slide decks, or scripts with a matching name.
- If a GitHub repo was provided, also read the README, top-level source files, and recent
  `git log --oneline -20`.

Summarize in one sentence what this episode covers. Use that summary to inform the metadata —
do **not** write generic descriptions.

### 3. Generate sidecars

For each video `foo.mp4`, write `foo.yaml` beside it. Follow the schema in
`references/yaml-schema.md`. Rules:

- **Title**: primary keyword within the first 40 characters. Under 70 chars total.
  For series, use a consistent `Series Name Ep. N: Topic` pattern.
- **Description**: first 150 characters must contain the core keyword and a clear promise of
  what the viewer learns. Include timestamps if a transcript is available.
- **Tags**: 8–15 tags, mixing broad (`python tutorial`) and specific (`python f-strings`).
- **Privacy**: default `public`, unless the user specified otherwise.

### 4. Show before writing

Print every generated YAML in a single review block and ask for confirmation. Only write files
after the user approves.

### 5. Upload

Ask the user whether to dry-run or execute.

Dry run:
```bash
ytstudio videos upload <directory>
```

Execute:
```bash
ytstudio videos upload <directory> --execute
```

After the run, report: how many uploaded, how many skipped (already have `video_id`), and the
remaining daily quota estimate.

## Guardrails

- **Never** invent video content. If you can't find source material, say so and ask.
- **Never** run `--execute` without explicit user confirmation.
- **Never** modify an existing `.yaml` that already contains a `video_id` — that video is live.
- Warn if a batch exceeds 6 videos (default daily quota).
```

---

## YAML sidecar schema

One sidecar per video, same basename:

```yaml
title: "Python Basics Ep. 1: Variables & Data Types"  # required, ≤100 chars
description: |                                       # required, keyword in first 150 chars
  Learn the fundamental building blocks of Python...

  00:00 Intro
  01:23 Variables
  05:45 Data Types

  #Python #LearnToCode
tags:                                                # optional but recommended, 8–15
  - Python tutorial
  - Python for beginners
  - programming basics
privacy: public                                      # public | unlisted | private
publish_at: "2026-11-01T10:00:00+05:30"              # optional, must be future + timezone-aware
```

`video_id` is written back by `ytstudio-cli` after a successful upload — do not set it manually.

Full field reference: [`skills/metatube/references/yaml-schema.md`](skills/metatube/references/yaml-schema.md).

---

## Usage examples

### Single video

```
episodes/
├── python-intro.mp4
└── python-intro.yaml
```

```bash
ytstudio videos upload ./episodes/python-intro.mp4 --execute
```

### Educational series

```
python-series/
├── episode-01.mp4  episode-01.yaml
├── episode-02.mp4  episode-02.yaml
└── episode-03.mp4  episode-03.yaml
```

```bash
ytstudio videos upload ./python-series --execute
```

Interrupted by quota? Re-run the same command — anything with a `video_id` is skipped, and only
the failures are retried.

### From a GitHub repo

```
> /metatube generate metadata for https://github.com/me/my-python-course
```

Claude clones/reads the repo, infers the curriculum from the code structure and README, and
generates sidecars for videos in the repo's `videos/` (or wherever you point it).

---

## Roadmap

- [ ] `SKILL.md` v1 with single-video workflow
- [ ] Series/batch workflow with consistent title patterns
- [ ] GitHub repo ingestion (clone + analyze)
- [ ] Transcript-aware timestamps (`*.srt` / `*.vtt` parsing)
- [ ] Thumbnail suggestions (prompt for design, don't generate yet)
- [ ] Playlist creation + auto-assignment after batch upload
- [ ] Pre-flight quota estimator
- [ ] `validate-sidecars.sh` with lint rules (title length, tag count, keyword placement)

---

## Contributing

1. Fork and branch (`feat/playlist-support`).
2. Keep `SKILL.md` instructions declarative — no hardcoded paths or channel names.
3. Add an example under `examples/` for any new workflow.
4. Test with a **dry run** first. Never commit real OAuth credentials or `client_secret.json`.

---

## License

MIT — see [`LICENSE`](LICENSE).

---

## Acknowledgements

- [`ytstudio-cli`](https://github.com/jdwit/ytstudio-cli) — the upload engine.
- Claude Code plugin/skill docs — for the `allowed-tools` and skill structure conventions.

---

## Review & Suggestions

**Overall assessment:** Solid, well-structured product requirements document. The core idea is clean and pragmatic: Claude does content-aware analysis + metadata generation; `ytstudio-cli` owns the deterministic, resumable, quota-aware upload path. Separation of concerns is excellent, and the “show YAML → confirm → write → dry-run/execute” loop is the right safety posture.

### Strengths

- Clear problem statement and motivation (inconsistent titles, weak descriptions/tags, quota burn).
- Good architecture diagram and explicit design principle (“skill never talks to the YouTube API”).
- Sensible guardrails: never invent content, never `--execute` without confirmation, never overwrite live `video_id` sidecars, quota warning.
- Practical YAML schema with SEO rules (keyword placement, length limits, series naming pattern).
- Realistic quota note (≈6 uploads/day on default quota) and emphasis on dry-run.
- Roadmap is prioritized and realistic.
- Repo layout follows Claude plugin/skill conventions.

### Gaps & Issues to Address

1. **`ytstudio-cli` is underspecified**
   - Exact command surface, flags, exit codes, and how it writes `video_id` back into the YAML should be documented in a `references/cli-contract.md`.

2. **Discovery & input handling are incomplete**
   - What about already-uploaded videos, multiple candidates with the same basename, or videos living outside the analyzed folder?
   - GitHub repo flow needs details on depth, branch, private repos, and where video files live relative to source material.
   - Transcript parsing logic and fallback when `*.srt`/`*.vtt` are missing should be specified.

3. **Metadata quality rules need more precision**
   - Add guidance on clickbait avoidance, brand consistency, and language support.
   - Provide description templates for chapters, links, CTAs, and series navigation.
   - Clarify banned/overused tags.

4. **Error handling & observability**
   - Define behavior on partial batch failure, OAuth token expiry, or quota exhaustion.
   - Add logging / status files and remaining-quota reporting.
   - Flesh out `validate-sidecars.sh` rules.

5. **Security & secrets**
   - Document how the skill behaves if `ytstudio` is not authenticated.
   - Explicitly state that the skill must never touch `client_secret.json` or token stores.

6. **Plugin packaging**
   - Show a concrete `.claude-plugin/plugin.json`.
   - Add versioning strategy and a basic test harness.

7. **Edge cases**
   - Detection of already-live videos.
   - Non-English content.
   - Very long series and playlist creation.
   - Interaction of `publish_at` with quota and dry-run.

### Suggested Improvements

**Immediate (v1)**
- Flesh out `references/yaml-schema.md` and `references/seo-guide.md` with concrete examples and anti-patterns.
- Add an explicit CLI contract section.
- Make the “show YAML → confirm” step mandatory and support bulk edit before writing.
- Add a pre-flight check: count videos, estimate quota cost, warn if > remaining quota.
- Document exact `allowed-tools` and required environment variables.

**Near-term**
- Transcript → chapter timestamp extraction.
- Consistent series naming helper.
- Status tracking file (e.g. `.metatube-status.json`) for idempotent re-runs.

**Design polish**
- Prefer a single command surface (`/metatube generate`, `/metatube upload --dry-run`, etc.).
- Refuse to proceed if no source material is found for a video.
- Run validation before offering upload commands.

### Clarity & Completeness Score

| Area                    | Score | Notes                                      |
|-------------------------|-------|--------------------------------------------|
| Problem & motivation    | 9/10  | Clear and convincing                       |
| Architecture            | 9/10  | Excellent separation                       |
| Workflow                | 7/10  | Good skeleton, missing edge cases          |
| Schema & SEO rules      | 7/10  | Solid start, needs more concrete guidance  |
| Safety / Guardrails     | 8/10  | Strong, can be tightened further           |
| Tooling / CLI contract  | 4/10  | Biggest gap                                |
| Packaging & testing     | 5/10  | Skeleton only                              |
| Roadmap                 | 8/10  | Realistic and prioritized                  |

**Bottom line:** Strong foundation. The main risks are the underspecified `ytstudio-cli` dependency and incomplete discovery/error-handling paths. Address those and MetaTube becomes production-ready for educational series workflows.
