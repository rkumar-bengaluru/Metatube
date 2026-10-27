# MetaTube

A Claude Code plugin that turns a **folder of training videos and their source material** into
YouTube videos with content-aware, search-friendly metadata.

Point it at the folder you used to make your videos (rendered files, scripts, notes,
transcripts) and MetaTube will:

1. **Analyze** what each video actually teaches.
2. **Generate** a YAML sidecar per video: title, description, tags, category, language.
3. **Publish** through [`ytstudio-cli`](https://github.com/jdwit/ytstudio-cli): either apply the
   metadata to videos you already uploaded in YouTube Studio (`update` mode), or upload the
   videos themselves (`upload` mode).

Claude reasons over the content; `ytstudio-cli` does the deterministic YouTube API work.
Every change is previewed (dry run) and only applied after you say yes.

> Design spec: [`docs/superpowers/specs/2026-10-27-metatube-design.md`](docs/superpowers/specs/2026-10-27-metatube-design.md)

---

## Why this exists

Publishing a training series by hand is tedious and the metadata suffers:

- Titles drift across episodes.
- Descriptions are copy-pasted and say little about what the video covers.
- Tags are an afterthought, so the video doesn't show up for queries it answers.

MetaTube reads what each video is about and writes metadata so that **every query the video
genuinely answers can find it**, without keyword stuffing or misleading titles (which YouTube
penalizes).

---

## How it works

```
┌──────────────────────────┐
│ Project folder           │  episode-01.mp4, episode-01.md (script/notes),
│                          │  episode-01.srt (optional transcript), README …
└────────────┬─────────────┘
             │  /metatube:generate
             ▼
┌──────────────────────────┐
│ MetaTube skill (Claude)  │  read + analyze → draft sidecars → you review
│                          │  → write episode-01.yaml
└────────────┬─────────────┘
             │  /metatube:publish --mode update | upload
             ▼
┌──────────────────────────┐
│ ytstudio-cli (pinned)    │  dry run → you confirm → --execute
└────────────┬─────────────┘
             ▼
          YouTube
```

**Design principle:** MetaTube never calls the YouTube API itself. It writes sidecars and shells
out to `ytstudio-cli`, so every upload can be reviewed and reproduced without Claude.

---

## Two phases: the private-upload lock

Google locks videos uploaded through the API to **private** when the Google Cloud project has
not passed the **YouTube API Services compliance audit** (projects created after July 2020).
They can't be made public in Studio either. So:

| Phase | When | How videos get onto YouTube | MetaTube mode |
| --- | --- | --- | --- |
| **1** | Until the audit passes | You upload in YouTube Studio | `--mode update`: applies title, description, tags |
| **2** | After the audit passes | MetaTube uploads via ytstudio | `--mode upload` |

In phase 1, set **category, made-for-kids, language and visibility** in Studio's upload dialog;
`ytstudio videos update` only changes title, description and tags. MetaTube lists the values
to pick.

### Applying for the audit

1. Open the [YouTube API Services – Audit and Quota Extension Form](https://support.google.com/youtube/contact/yt_api_form)
   signed in as the account that owns the Cloud project.
2. Have ready: legal/organization name, website, contact email, the **project number**, a plain
   description of the tool, whether you commercialize YouTube data (no), and screenshots or a
   short screencast of the tool working.
3. Describe it accurately: a single-owner internal tool that uploads training videos to its own
   channel and edits their metadata; no other users; no storing or reselling data.
4. Tick the quota-extension option only if you need more uploads per day.
5. Expect days to weeks; Google replies by email. When it passes, set `audit_passed: true` in
   `~/.config/metatube/config.yaml` (or re-run `/metatube:setup`).

Google's guide: [Quota and Compliance Audits](https://developers.google.com/youtube/data/guides/quota_and_compliance_audits).

---

## Prerequisites

| Requirement | Notes |
| --- | --- |
| **Claude Code** | With plugin support. |
| **Python ≥ 3.12** and **uv** | `ytstudio-cli` is a Python tool, installed with `uv tool install`. |
| **`ytstudio-cli` 0.4.2** | Pinned. `/metatube:setup` offers to install it. |
| **Google Cloud project** | **YouTube Data API v3** enabled. Setup also enables the **YouTube Analytics API** (ytstudio requests analytics scopes). |
| **gcloud** (optional) | Used only to check/enable the APIs. |
| **A YouTube channel** | Uploads fail for Google accounts without one; create it in YouTube first. |

> **Weekly login.** The OAuth app runs in **Testing** mode, and Google expires Testing-mode
> logins after **7 days**. MetaTube checks the login before every publish and walks you through
> `ytstudio login` when it has expired. To avoid this, move the consent screen to
> **In production** (unverified apps show a one-time warning screen).

---

## Install

```bash
git clone https://github.com/rkumar-bengaluru/Metatube.git
```

Then in Claude Code:

```
/plugin marketplace add ./Metatube
/plugin install metatube
```

---

## Setup: `/metatube:setup`

Every step checks first and is skipped if already done, so it's safe to re-run.

1. **Tooling.** Checks Python, uv, gcloud and `ytstudio --version`; offers
   `uv tool install ytstudio-cli==0.4.2`.
2. **APIs.** Enables YouTube Data API v3 / YouTube Analytics API with gcloud if they're off.
3. **Consent screen + OAuth client (manual, ~5 minutes).** Google offers no API for these, so
   MetaTube gives you the click path:
   - *OAuth consent screen* → **External** → app name, support email → add yourself as a
     **test user** → leave in **Testing**.
   - *Credentials* → *Create credentials* → *OAuth client ID* → **Desktop app** → download JSON.
4. **Init.** `ytstudio init --client-secrets <path>`. MetaTube only passes the path; it never
   reads, copies or commits the file.
5. **Login.** You run `! ytstudio login` and approve in the browser. The "Google hasn't verified
   this app" screen is expected for a Testing app.
6. **Verify.** Confirms the login works and shows your channel name for you to confirm.
7. **Defaults + brand voice.** Picks a default category and offers to create a brand voice file
   (`ytstudio profile brand edit`) that keeps the tone consistent.
8. **Audit status.** Asks whether the audit has passed and explains the steps above if not.
9. **Config.** Writes `~/.config/metatube/config.yaml` (identifiers and defaults only, never
   tokens).

---

## Usage

### Project folder layout

```
my-video-project/
├── episode-01.mp4        # .mp4 .mov .mkv .webm
├── episode-01.md         # script / notes (required: no source material, no metadata)
├── episode-01.srt        # optional transcript → chapter timestamps
├── episode-01.jpg        # optional thumbnail (.jpg/.png ≤ 2 MB), upload mode only
├── README.md             # optional, folder-level context
└── episode-01.yaml       # written by MetaTube after you approve
```

### Phase 1: upload in Studio, update with MetaTube

1. Upload the videos in YouTube Studio. Leave each title as the file name (Studio's default),
   which is how MetaTube matches them. Set category, made-for-kids and visibility there.
2. `/metatube:generate ./my-video-project`: review the drafts, edit, approve.
3. `/metatube:publish ./my-video-project --mode update`: confirm each file ↔ video match, review
   the old vs. new metadata, then approve to apply.

### Phase 2: upload with MetaTube

1. `/metatube:generate ./my-video-project`: review and approve.
2. `/metatube:publish ./my-video-project --mode upload`: login and quota check, dry run, then
   approve to upload.

Interrupted by quota? Run the same command again. Anything with a `video_id` is skipped.

The same thing by hand, without Claude:

```bash
ytstudio videos upload ./my-video-project             # dry run
ytstudio videos upload ./my-video-project --execute   # upload
ytstudio videos update <video-id> --title "…" --description "…" --tags "a,b"   # dry run; add --execute
```

---

## Sidecar schema

One sidecar per video, same basename. This is ytstudio-cli's schema; **unknown keys are
rejected**.

```yaml
title: "Getting Started with the X Repo: Install & First Run"   # required, ≤ 100 chars (aim ≤ 70)
description: |                                                  # keyword + promise in first ~150 chars
  Learn how to clone, install and run the X repo …

  00:00 Intro
  01:23 Cloning the repo
  05:45 First run

  #GitHub #OpenSource
tags: [x repo tutorial, github tutorial, …]   # 8–15, all grounded in the video's content
category_id: "28"              # required. 28 = Science & Technology, 27 = Education
privacy: public                # public | unlisted | private
made_for_kids: false           # true only for content aimed at children under 13 (COPPA)
default_language: en
default_audio_language: en
# publish_at: 2026-11-01T10:00:00+05:30   # optional; must be future + timezone-aware; forces private
# video_id / uploaded_at: written by ytstudio (upload) or MetaTube (update matching). Never edit.
```

MetaTube defaults: `privacy: public`, `category_id: "28"`, `made_for_kids: false`, language `en`.
Chapter timestamps are only added when a transcript (`.srt`/`.vtt`) exists.

---

## Guardrails

- Nothing is uploaded or updated (`--execute`) without your explicit yes in the session.
- Metadata is never applied to a video whose match you haven't confirmed.
- An existing `video_id` is never changed, and a sidecar with one is never uploaded again.
- No source material means no draft: MetaTube never invents what a video covers.
- MetaTube never reads, prints, copies or commits OAuth client secrets or tokens.

---

## Quota

Default: 10,000 units/day per project, resetting at midnight Pacific. Check your project's
**Quotas** page, since Google's current guide also describes a separate daily upload allocation.

| Action | Approx. cost |
| --- | --- |
| List / read | 1 unit |
| Update metadata (`videos update`) | 50 units |
| Upload (`videos.insert`) | ~1,600 units (≈ 6 uploads/day) |

---

## Roadmap

- [ ] v1: setup, generate, publish (`update` + `upload` modes)
- [ ] GitHub repo ingestion (clone + analyze code, docs, commit history)
- [ ] Playlist creation and assignment after a batch
- [ ] Thumbnail suggestions
- [ ] Chrome-driven Cloud Console setup
- [ ] Production OAuth app (no weekly re-login)

---

## Contributing

1. Branch per change (`feat/playlist-support`).
2. Keep `SKILL.md` declarative: no hardcoded paths or channel names.
3. Add an example under `examples/` for any new workflow.
4. Dry-run first. Never commit `client_secret*.json` or tokens.

## License

MIT, see [`LICENSE`](LICENSE).

## Acknowledgements

- [`ytstudio-cli`](https://github.com/jdwit/ytstudio-cli) by Jelmer de Wit: the YouTube engine underneath.
