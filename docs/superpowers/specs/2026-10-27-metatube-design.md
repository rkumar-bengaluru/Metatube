# MetaTube v1 — Design

Date: 2026-10-27
Status: draft for approval

## 1. Intent

MetaTube is a Claude Code plugin that turns a local folder of rendered training videos plus
their source material into YouTube uploads with high-quality, content-aware metadata.

The videos are **training videos about GitHub repos**, aimed at developers. The owner is a
single person uploading to **their own, newly created channel**. The point of the tool:

- Claude reads what each video actually covers and writes metadata so that **every query the
  video genuinely answers surfaces it** (search discoverability is the success measure).
- Getting from "Google Cloud project with YouTube Data API enabled" to "first upload" is
  automated as far as Google allows, so setup is a guided command, not a wiki page.
- Claude never talks to the YouTube API itself. It drives **`ytstudio-cli`** (the base tool),
  so every upload is reproducible from the sidecar files without Claude in the loop.

## 2. Goals, non-goals, anti-goals

**Phasing (owner's decision).** Uploads from an unaudited API project are locked to private
(see §3), so:

- **Phase 1 (day one):** the owner uploads videos by hand in YouTube Studio; MetaTube generates
  the metadata and applies it to those already-uploaded videos (`update` mode).
- **Phase 2 (after the YouTube API compliance audit passes):** MetaTube also uploads
  (`upload` mode). Both modes ship in v1; the owner picks per run.

**Goals (v1)**

1. `/metatube:setup` — idempotent, guided setup including Google OAuth via ytstudio-cli, plus
   guidance for the API compliance audit request.
2. `/metatube:generate <folder>` — read videos + source material, draft one YAML sidecar per
   video, show all drafts for review, write only after approval.
3. `/metatube:publish <folder> --mode update|upload` — apply approved sidecars:
   - `update` (default while unaudited): match each local video to its Studio-uploaded video,
     dry-run, then apply title/description/tags on explicit confirmation.
   - `upload`: auth + quota pre-flight, dry run, `--execute` only on explicit confirmation.
4. Rewrite `README.md` so it is accurate against ytstudio-cli 0.4.2 (see §9).

**Non-goals (v1)** — GitHub repo URL ingestion (clone + analyze), playlists, thumbnail
generation, multi-channel use, publishing the OAuth app to Production, non-English metadata,
changing privacy/category/made-for-kids on existing videos through the API (set in Studio).

**Anti-goals** — it fails even if it "works" when:

- Metadata claims something the video does not cover, or uses keyword stuffing / misleading
  titles (violates YouTube spam policy, gets videos demoted — the opposite of the goal).
- Anything touches `client_secret*.json` or ytstudio's token store beyond passing a path.
- An upload or update runs (`--execute`) without the user's explicit yes in that session.
- Quota is burned on a run that was going to fail on auth.
- A video gets uploaded twice, or metadata is applied to the wrong video.
- An existing `video_id` in a sidecar is changed or removed.

## 3. Constraints and facts about the base tool

Verified by reading ytstudio-cli source at v0.4.2 (commit `242ee3a`, 2026-07-01):

- Install: Python ≥ 3.12, `uv tool install ytstudio-cli==0.4.2` (pinned). Owner's machine has
  Python 3.12.10, uv 0.5.11, gcloud 545. Platform: Windows 11 (ytstudio supports Windows via
  `msvcrt` locking).
- Auth: `ytstudio init --client-secrets <path>` copies the client into
  `~/.config/ytstudio-cli/client_secrets.json`; `ytstudio login` runs a local-server OAuth flow
  on port 9876 (one browser consent). `--headless` exists. Scopes include `youtube.force-ssl`
  (covers upload) and YouTube Analytics read scopes.
- **`ytstudio status` exits 0 even when not authenticated or expired** (prints a yellow
  message). It cannot be used as a pass/fail auth check by exit code. Commands that hit the
  API (e.g. `ytstudio videos list -n 1 -o json`) exit 1 with "Session expired or revoked" on
  `RefreshError`.
- Upload: `ytstudio videos upload <file|dir> [--execute] [--max N]`. Dry-run by default.
  Video extensions: `.mp4 .mov .mkv .webm`. Sidecar = same basename `.yaml`. Thumbnail = same
  basename `.jpg`/`.png` ≤ 2 MB (near-miss extensions fail fast). After each success it writes
  `video_id` + `uploaded_at` back into the sidecar; re-runs skip those. On `quotaExceeded` it
  stops cleanly and exits non-zero.
- Sidecar schema (pydantic, **`extra = forbid`** — unknown keys are rejected):
  `title` (1–100 chars, required), `description`, `privacy` (private|unlisted|public),
  `publish_at` (tz-aware, future; **forces privacy=private**), `tags` (list),
  `category_id` (**required**, string), `default_language`, `default_audio_language`,
  `made_for_kids` (bool), `video_id`, `uploaded_at`.
  ⇒ MetaTube cannot store its own bookkeeping inside sidecars.
- Update: `ytstudio videos update <id> [--title] [--description] [--tags "a,b,c"] [--execute]`.
  Dry-run by default. **Only title, description and tags** — not category, language,
  privacy or made-for-kids. ~50 units per update. `ytstudio videos list -n N -o json` returns
  id, title, privacy, published_at (1 unit).
- Profiles: one per channel, plus an optional per-profile `brand.md` ("brand voice")
  read via `ytstudio profile brand show` (exits non-zero if unset).
- ytstudio ships its own agent skill; MetaTube sits on top of it, it does not replace it.

Google-side constraints:

- The consent screen and a **Desktop app** OAuth client cannot be created through any public
  API/gcloud for an External app. They are manual Console steps.
- The OAuth app stays in **Testing** mode (owner's decision). Google expires refresh tokens for
  Testing-mode apps after **7 days**, so the user re-logs in weekly.
- `videos.insert` ≈ 1,600 units; default quota 10,000/day ⇒ ~6 uploads/day. Quota resets at
  midnight Pacific. (Google's current audit guide describes the default as 10,000 units plus a
  separate allocation of 100 `videos.insert` calls/day; the builder should confirm which applies
  in the project's Quotas page and word the quota pre-flight accordingly.)
- **Unaudited projects:** videos uploaded via `videos.insert` from API projects created after
  28 July 2020 that have not passed the YouTube API Services compliance audit are locked to
  private, regardless of the requested privacy. Testing-mode apps are unaudited. Audit request:
  the *YouTube API Services – Audit and Quota Extension Form*
  (https://support.google.com/youtube/contact/yt_api_form); process guide:
  https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits .
  The lock applies to inserts; updating metadata on Studio-uploaded videos is expected to work
  day one — verify on the first real video (§10).
- The owner has already created the channel.

## 4. Decisions made by the owner

- Base tool is ytstudio-cli; Claude Code uses it beneath the MetaTube skill/plugin.
- Single user, own channel, for now.
- OAuth app in **Testing mode with weekly re-login**; MetaTube detects expiry and guides re-login.
- Setup flow shape (§6), including writing a small local config so later runs are silent.
- v1 input is a **local project folder**; GitHub repo ingestion is later.
- Default `privacy: public` (owner reviews every draft anyway).
- Supported video types: whatever ytstudio accepts (`.mp4 .mov .mkv .webm`).
- Claude's job in generate: read the content and write metadata so any relevant query finds the
  video.
- `made_for_kids`: delegated to Claude — see §5.
- **Phase 1 = manual Studio upload + MetaTube `update`; phase 2 = MetaTube `upload` once the
  audit passes.** Both modes built now, chosen by a command option.
- Setup should also explain how to apply for the audit.

## 5. Calls made by Claude (owner can override)

- **`made_for_kids: false`** by default. These are developer training videos; "made for kids"
  is a COPPA designation for content aimed at under-13s and would disable comments,
  notifications, end screens and more. Overridable per sidecar.
- **`category_id: "28"` (Science & Technology)** by default for GitHub-repo training content;
  `"27"` (Education) is the alternative. Asked once at setup, stored in config.
- **`default_language` / `default_audio_language`: `en`.**
- **Pin ytstudio-cli 0.4.2**; upgrading is a deliberate change to the plugin (bump pin, re-test).
- **Console steps are text-guided** (numbered click path, wait for the JSON). Driving the
  user's Chrome is a possible later enhancement, not v1.
- **Also enable the YouTube Analytics API** in setup, since ytstudio requests analytics scopes.
- **Brand voice**: setup offers to create `brand.md` via ytstudio; generate reads it if present.
- **Chapter timestamps only from a transcript** (`.srt`/`.vtt`), never inferred from a script.
- **Force `PYTHONUTF8=1`** when invoking ytstudio on Windows: it reads sidecars with
  `Path.read_text()` (no explicit encoding), which would use cp1252 and break on em dashes /
  non-ASCII in descriptions. Builder must verify this with a sidecar containing `—` and `é`.
- **Remove the "Review & Suggestions" section** from README — this spec supersedes it.
- **Packaging:** the repo root is the plugin, with a local `marketplace.json` so it installs
  via `/plugin marketplace add <path>`; commands are namespaced `/metatube:setup`,
  `/metatube:generate`, `/metatube:publish`.
- **Default mode** for `publish` comes from config: `update` until the owner sets
  `audit_passed: true` (setup asks; the owner can flip it any time).
- **Matching for `update`:** Studio sets a new upload's title to the file's basename, so
  MetaTube matches local `<name>.mp4` to the channel video whose current title equals `<name>`
  (case-insensitive, extension stripped). Every match is shown for confirmation; ambiguous or
  missing matches ask the user for the video id or URL. The confirmed id is written to the
  sidecar as `video_id` — this also stops a later `upload` run from uploading it twice.
- **Folders with unpaired videos (`upload` mode):** ytstudio rejects a whole folder if any
  video lacks a sidecar or any sidecar lacks a video. If the folder is fully paired, MetaTube
  uses the folder command (reproducible by hand). Otherwise it runs ytstudio once per ready
  file, stops at the first `quotaExceeded`, applies `--max` itself, and prints the exact
  per-file commands it ran.

## 6. `/metatube:setup`

Every step checks first and is skipped if already satisfied, so re-running is safe.

1. **Tooling.** Check `python --version` ≥ 3.12, `uv`, `gcloud`, and `ytstudio --version`
   == 0.4.2. If ytstudio is missing or a different version, offer
   `uv tool install ytstudio-cli==0.4.2` (ask before installing).
2. **APIs.** Ask for the GCP project id (or read `gcloud config get-value project` and
   confirm). `gcloud services list --enabled` → if `youtube.googleapis.com` or
   `youtubeanalytics.googleapis.com` is missing, offer `gcloud services enable …`. If gcloud is
   not logged in, tell the user to run `! gcloud auth login` and stop this step (optional step;
   the user may say it's already done).
3. **Consent screen + OAuth client (manual).** If `~/.config/ytstudio-cli/client_secrets.json`
   already exists, skip to step 5. Otherwise print the click path, with direct Console links
   for the project:
   - OAuth consent screen → External → app name, support email → add yourself as **test
     user** → leave in **Testing**.
   - Credentials → Create credentials → OAuth client ID → **Desktop app** → Download JSON.
   Then ask for the downloaded file's path. Never read, copy, move, or print its contents.
4. **Init.** `ytstudio init --client-secrets <path>`. Then tell the user they may delete the
   download (ytstudio keeps its own copy) — do not delete it for them.
5. **Login.** Ask the user to run `! ytstudio login` (browser consent; Claude's shell can't
   click the consent screen). Explain the "Google hasn't verified this app" screen is expected
   for a Testing app.
6. **Verify.** Run `ytstudio videos list -n 1 -o json` (exit code = real auth check) and
   `ytstudio status` (channel title). Show the channel title and ask the user to confirm it is
   the right channel. If no channel is found, stop and tell them to create one in YouTube.
7. **Defaults + brand voice.** Ask the category (default 28). Offer to create a brand voice
   via `ytstudio profile brand edit` (or `brand set --file`).
8. **Audit.** Ask whether the project has passed the YouTube API compliance audit. If not,
   explain the private-lock, set `audit_passed: false`, and show the audit guidance from
   `references/audit-guide.md`: form link, what it asks (legal/org name, website, contact,
   project number, how the client uses the API, whether it commercializes YouTube data,
   screenshots or a short screencast of the tool), and tips (describe it accurately as a
   single-owner internal tool uploading to its own channel; tick the quota-extension option
   only if needed; expect days to weeks; Google replies by email). MetaTube does not submit
   the form.
9. **Write config** (§8) and print a one-screen summary: channel, profile, ytstudio version,
   defaults, mode, and a reminder that login expires every 7 days.

## 7. Generate and upload

### 7.1 `/metatube:generate <folder>`

1. **Discover** videos (`.mp4 .mov .mkv .webm`, non-recursive in v1) in the folder. Flag
   other video-like files (`.avi`, `.wmv`, `.m4v`, …) as unsupported, don't skip silently. No
   videos → ask where they are; don't guess.
2. **Partition.** Videos whose sidecar has `video_id` are live: list them, never touch them.
   Videos with an existing sidecar but no `video_id`: ask whether to regenerate or keep.
3. **Gather source** per video, by same basename first: `<name>.md/.txt` (script/notes),
   `<name>.srt/.vtt` (transcript), slides (`.pdf`/`.pptx` — read text where possible), plus
   folder-level `README.md`, and any linked GitHub repo URL mentioned in the notes (read its
   public README only if reachable; no cloning in v1). **No source material → refuse to draft
   that video** and say so.
4. **Analyze.** For each video, a one-sentence summary of what it teaches and the concrete
   queries a developer would type to find it (repo name, tool, task, error messages, concepts).
   Read `ytstudio profile brand show` if set.
5. **Draft sidecar** with config defaults (privacy, category, language, made_for_kids) and:
   - **Title:** ≤ 70 chars (hard limit 100), primary query phrase in the first ~40 chars;
     series pattern `Series Name Ep. N: Topic` when files are numbered/named as a series.
   - **Description:** first ~150 chars state the core keyword and what the viewer will be able
     to do; then a short body; chapters only from a transcript (`00:00` first, ≥ 3 chapters,
     ≥ 10 s apart — YouTube's chapter rules); links found in the notes (repo URL, docs);
     2–3 hashtags.
   - **Tags:** 8–15, mixing broad and specific, total ≤ 500 chars, every tag grounded in
     content. No competitor/brand names that aren't in the video.
6. **Review gate.** Show all drafts in one block with the summary used for each. The user
   approves, edits ("make ep 2's title shorter"), or rejects per video. Write files only after
   approval.
7. **Validate** with a dry run: `ytstudio videos upload <folder>` (no `--execute`). Report
   any schema errors and fix the drafts.

In `update` mode the dry-run validation in step 7 is skipped when the folder isn't fully
paired; MetaTube validates sidecars against the §3 schema itself.

### 7.2 `/metatube:publish <folder> --mode update`

1. **Auth pre-flight** as in 7.3 step 1.
2. **Match** (see §5): `ytstudio videos list -n 50 -o json`; pair each approved sidecar
   without `video_id` to a channel video; show the table (local file → video title, id,
   privacy, upload date); user confirms or corrects; write `video_id` into each confirmed
   sidecar. Sidecars that already have `video_id` use it directly.
3. **Dry run** per video: `ytstudio videos update <id> --title … --description … --tags …`;
   show current vs. new.
4. Ask explicitly: apply? Only on yes, re-run each with `--execute`.
5. **Report:** updated (with Studio links `https://studio.youtube.com/video/<id>/edit`),
   failed with reason, and a reminder of what MetaTube can't set on existing videos —
   category, language, made-for-kids, visibility — to check in Studio (with the sidecar's
   intended values listed).
6. Re-running `update` on a video is allowed (metadata can be revised); it always shows the
   diff and asks again.

### 7.3 `/metatube:publish <folder> --mode upload`

1. **Auth pre-flight:** `ytstudio videos list -n 1 -o json`. Exit 1 / "Session expired" →
   stop, explain the 7-day Testing-mode expiry, ask the user to run `! ytstudio login`, then
   re-check. No quota spent on uploads before this passes.
2. **Quota pre-flight:** count pending sidecars (no `video_id`) × 1,600 units. If > 6, warn and
   propose `--max 6`. MetaTube can't read remaining quota from Google; it states the estimate
   as an estimate.
3. **Dry run**, show its output.
4. Ask explicitly: execute? Only on yes: `ytstudio videos upload <folder> --execute [--max N]`.
5. **Report:** uploaded (with `https://youtu.be/<id>` links), skipped (already live), failed
   (with reason), estimated quota used. On `quotaExceeded`: say it resets at midnight Pacific
   and that re-running the same command resumes. If ytstudio printed a `video_id` because the
   write-back failed, surface it prominently and tell the user to paste it into the sidecar.
   If config says `audit_passed: false` and the user still chooses upload, warn before the run
   that videos will be locked private, and say so again in the report.

### 7.4 Guardrails (in SKILL.md)

- Never `--execute` without an explicit yes in the current session.
- Never change or remove an existing `video_id`; never upload a sidecar that has one.
- Never apply metadata to a video whose match the user hasn't confirmed.
- Never invent content; no source → no draft.
- Never read/print/copy/commit client secrets or token files.
- Never add non-schema keys to sidecars (ytstudio rejects them).
- Always run ytstudio with `PYTHONUTF8=1`.

## 8. Packaging

```
<repo root>/                        # the repo root is the plugin
├── .claude-plugin/plugin.json      # name, version, description
├── .claude-plugin/marketplace.json # local marketplace for /plugin install
├── commands/                       # setup.md, generate.md, publish.md → /metatube:*
├── skills/metatube/
│   ├── SKILL.md                    # workflow + guardrails above
│   └── references/
│       ├── cli-contract.md         # the ytstudio facts in §3, pinned to 0.4.2
│       ├── sidecar-schema.md       # fields, defaults, examples
│       ├── seo-guide.md            # title/description/tag rules + anti-patterns
│       ├── setup-console-steps.md  # the manual Console click path
│       └── audit-guide.md          # how to apply for the API compliance audit
├── examples/single-video/ , examples/series/   # source + expected sidecar, no real video files
└── README.md
```

- `allowed-tools`: `Bash(ytstudio *)`, `Bash(gcloud services *)`, `Bash(gcloud config get-value *)`,
  `Read`, `Write`, `Glob`, `Grep`. Upload with `--execute` must still go through user
  confirmation in-conversation.
- **Config:** `~/.config/metatube/config.yaml` — `ytstudio_profile`, `channel_id`,
  `channel_title`, `gcp_project`, `ytstudio_version`, `audit_passed`, `defaults` (privacy,
  category_id, language, made_for_kids). Identifiers only; no tokens. Lives outside any repo.
- Example `.mp4` files are not committed (size); examples contain source material and the
  expected sidecar.
- `.gitignore` adds `client_secret*.json`.

## 9. README rewrite (deliverable)

Replace the current README with an accurate one: what it is, prerequisites (with the 7-day
Testing note and how to move to Production later), the private-lock and how to apply for the
audit, `/metatube:setup` walkthrough, the phase-1 flow (upload in Studio → generate → review →
update) and phase-2 flow (generate → review → dry-run → upload), the correct sidecar schema from §3, quota table,
roadmap (GitHub ingestion, playlists, transcript-derived chapters improvements, thumbnails,
Chrome-driven Console setup, Production OAuth). Drop the fictional `scripts/validate-sidecars.sh`
— ytstudio's dry run is the validator. Remove the "Review & Suggestions" section.

## 10. Testing

- **Setup:** run on a machine state with nothing configured, then re-run to confirm every step
  skips. Simulate expiry by revoking the app at myaccount.google.com/permissions and confirm the
  upload pre-flight catches it.
- **Generate:** the two examples (single, series) produce sidecars that pass ytstudio's dry run;
  a video with no source is refused; a live sidecar is untouched; a UTF-8 description with `—`
  and `é` round-trips on Windows.
- **Update (day-one check):** owner uploads one short test video in Studio; MetaTube matches
  it, dry-runs, applies title/description/tags; confirm in Studio that they changed. If the
  API refuses updates from the unaudited project, stop and report — phase 1 depends on this.
- **Upload:** after the audit, one real upload of a short test video (owner present), then a
  re-run showing it skipped. Before the audit, confirm the warning fires and the video lands
  private.
- Plugin skill triggering: `/metatube` commands and natural-language requests both route to
  the skill.

## 11. Left to the builder

Exact wording of SKILL.md and command files, how commands share logic with the skill, the
format of the review block, example content, and whether the Console steps use deep links
per project id.
