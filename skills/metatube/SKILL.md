---
name: metatube
description: Generate search-friendly YouTube metadata (title, description, tags) from a folder of training videos and their scripts, notes and transcripts, then apply it to YouTube through ytstudio-cli - either updating videos already uploaded in YouTube Studio or uploading new ones. Also sets up ytstudio-cli and Google OAuth. Use when the user wants to set up MetaTube, generate or improve YouTube metadata/sidecars for their videos, or update/upload/publish videos to their channel.
allowed-tools:
  - Bash(uv run --project * metatube-helper discover *)
  - Bash(uv run --project * metatube-helper lint *)
  - Bash(uv run --project * metatube-helper auth-check)
  - Bash(uv run --project * metatube-helper match *)
  - Bash(uv run --project * metatube-helper quota *)
  - Bash(uv run --project * metatube-helper config show)
  - Bash(uv run --project * metatube-helper secrets-present)
  - Bash(uv run --project * metatube-helper walker-status *)
  - Bash(ytstudio status*)
  - Bash(ytstudio --version)
  - Bash(ytstudio videos categories*)
  - Bash(gcloud services list *)
  - Bash(gcloud config get-value *)
  - Read
  - Write
  - Glob
  - Grep
---

# MetaTube

You turn a folder of rendered training videos plus their source material into YouTube metadata,
and apply it through **ytstudio-cli 0.5.0** (the base tool). You never call the YouTube API
yourself. The audience is developers learning about GitHub repos.

## The helper

Deterministic work goes through `metatube-helper`, which lives next to this file. Run it as:

```
uv run --project "<this skill's base directory>/helper" metatube-helper <subcommand> ...
```

(The base directory is shown when this skill loads.) Every subcommand prints one JSON object.
Subcommands: `discover FOLDER`, `lint PATH`, `write-sidecar SIDECAR --from DRAFT`, `auth-check`,
`match FOLDER [--limit N]`, `set-video-id SIDECAR REF [--replace-deleted] [--source SOURCE]`,
`update SIDECAR [--execute]`, `upload FOLDER [--execute] [--max N]`,
`quota FOLDER --mode update|upload`, `config show`, `config set KEY VALUE`, `secrets-present`.
For Walker sources: `walker-status SOURCE [--repo NAME]`, `walker-sync SOURCE`,
`playlist-draft SOURCE --from DRAFT`, `playlist SOURCE [--execute] [--create-new]`,
`playlist-adopt SOURCE PLAYLIST_ID [--confirm]`. `match` and `quota` also accept a Walker source.

Read-only subcommands run without a prompt. Writes and anything with `--execute` ask the user
for permission each time; that prompt is part of the safety design, so don't ask the user to
pre-approve them.

Never run `ytstudio videos update` or `ytstudio videos upload` yourself: use the helper, which
passes long descriptions safely and forces UTF-8. Never write or edit a sidecar (`*.yaml` next to
a video) with the Write or Edit tool: write drafts elsewhere and use `write-sidecar`, which lints
the draft and refuses to change or drop a `video_id`. Raw `ytstudio` is fine for `status`, `init`,
`login` (user runs it), `videos categories`. ytstudio 0.5.0 has a `profile brand`
command, but MetaTube keeps its own `brand.md` (`config show` gives `brand_path`); don't call it.

References (read when the step needs them): `references/cli-contract.md`,
`references/sidecar-schema.md`, `references/seo-guide.md`, `references/setup-console-steps.md`,
`references/audit-guide.md`.

## Plain folders and Walker sources

Generate and publish take either kind of folder:

- **Plain folder**: videos and their notes side by side (`<stem>.mp4`, `<stem>.md`, `<stem>.srt`).
  Sidecars go next to the videos.
- **Walker source**: a folder with a `series.yaml` (a series) or a `walker.yaml` (a single Walker video)
  whose `format` starts with `walker/`. The videos aren't in it: Walker renders each one into its home
  (`$WALKER_HOME`, else `home:` in `~/.walker/config.yaml`, else `~/.walker`), one folder per render, e.g.
  `~/.walker/<repo>/series/<series name>/<episode>/video/<run id>/<series name>-<episode>.mp4`.
  The sidecar goes into that run folder, next to the video. MetaTube's own bookkeeping (repo name, video
  ids, playlist) goes in `metatube.yaml` in the source folder, never in a sidecar. A series gets one
  playlist; a single Walker video gets none.

`walker-status FOLDER` tells them apart: the error `not a Walker series or single-video folder` means a
plain folder. Pointed at one episode of a series, it names the series folder to use instead. If the user
points at Walker's home (`~/.walker/...`) rather than the source, it's a plain folder with no videos at
its top: ask for the source folder (the one with `series.yaml`).

## Guardrails (always)

- Never `--execute` (update or upload) without the user's explicit yes **in this session**, given
  after they saw the dry run.
- Never change or remove an existing `video_id`; never upload a sidecar that has one.
- `metatube.yaml` never overwrites a sidecar's `video_id`: the sidecar is the source of truth and
  `walker-sync` only copies ids from sidecars into the manifest. If they disagree, stop and show both.
- One playlist per series. The id in `metatube.yaml` is the only playlist MetaTube adds to; a playlist on
  the channel with the same title goes through `playlist-adopt` or `--create-new`, never a silent second one.
- Never apply metadata to a video whose match the user hasn't confirmed.
- Never invent content: no source material → no draft. Chapters only from a transcript.
- Never read, print, copy, move or commit OAuth client secrets or ytstudio token files. Only pass
  the path the user gives you to `ytstudio init`.
- Never add keys outside the sidecar schema (ytstudio rejects them).
- Keywords come only from what the video covers. No keyword stuffing, misleading titles, or brand
  names the video doesn't discuss.

---

## Workflow: setup

Every step checks first and skips if already done. Tell the user which steps were skipped.

1. **Tooling.** `python --version` (≥ 3.12), `uv --version`, `gcloud --version` (optional),
   `ytstudio --version`. If ytstudio is missing or not 0.5.0, ask, then run
   `uv tool install ytstudio-cli==0.5.0` (add `--force` when replacing another version).
2. **APIs.** Project id: argument, else `gcloud config get-value project` (confirm with the user).
   `gcloud services list --enabled --project <id>`; if `youtube.googleapis.com` or
   `youtubeanalytics.googleapis.com` is missing, ask, then `gcloud services enable <api> --project <id>`.
   If gcloud isn't logged in, ask the user to run `! gcloud auth login`, or let them say the APIs
   are already on and move on.
3. **Consent screen + OAuth client.** `secrets-present`. If true, skip to step 5. Otherwise show
   `references/setup-console-steps.md` with the project id filled in, and wait for the path of the
   downloaded JSON.
4. **Init.** `ytstudio init --client-secrets "<path>"`. Tell the user ytstudio now has its own copy
   and they may delete the download. Don't delete it for them.
5. **Login.** `auth-check`. If not `ok`, ask the user to run `! ytstudio login` and approve in the
   browser; the "Google hasn't verified this app" screen is expected for a Testing app (Advanced →
   continue). Re-run `auth-check` until `ok`.
6. **Channel.** `ytstudio status` → show the channel name and ask the user to confirm it's the right
   one. No channel → stop: they must create one in YouTube first. Save it:
   `config set channel_title "<name>"` (and `channel_id` if shown), `config set gcp_project <id>`.
7. **Defaults + brand voice.** Show the defaults (`config show`): public, category 28 (Science &
   Technology), English, made_for_kids false. Offer category 27 (Education) as the alternative and
   apply changes with `config set defaults.<key> <value>`. Brand voice is optional: `config show`
   gives `brand_path` and `brand_exists`. If it doesn't exist, offer to write a short brand voice
   (tone, audience, words to use/avoid, sign-off) to `brand_path` with the user's input.
8. **Audit.** Ask whether the Cloud project has passed the YouTube API compliance audit.
   Save `config set audit_passed true|false`. If false, explain: API uploads are locked private until
   it passes, so for now upload in Studio and use `/metatube:publish --mode update`. Then walk them
   through `references/audit-guide.md`. You never submit the form.
9. **Summary.** `config show` → one screen: channel, profile, ytstudio version, defaults, mode, and
   "your login expires every 7 days in Testing mode; MetaTube will tell you when to re-login".

## Workflow: generate

First `walker-status FOLDER`. Not a Walker source → **Plain folder**; otherwise → **Walker source**.

### Plain folder

1. `discover FOLDER`. Report `unsupported` files (not uploadable by ytstudio) and `orphan_sidecars`.
   No videos → ask where the videos are; don't guess.
2. Partition:
   - `live: true` → list them and leave them alone, unless the user explicitly asks to revise one;
     then keep its `video_id` exactly.
   - existing sidecar, not live → ask: regenerate or keep?
   - `has_source: false` → refuse to draft that video and say which files you looked for
     (`<stem>.md/.txt`, `<stem>.srt/.vtt`, `<stem>.pdf/.pptx`). Files listed in `thin_sources`
     were found but are empty or too short (under 20 words of notes, after any frontmatter):
     name them and ask for real notes or a transcript.
   - Even with `has_source: true`, if the notes turn out to be unrelated to a video (e.g. a copied
     command or template file), treat it as no source and say so.
   - `sidecar_error` set → show it; ask before overwriting.
3. Read the sources: notes, transcripts, slides (text where readable), the folder README, and the
   public README of any GitHub repo URL in the notes if you can reach it (no cloning).
   If `config show` says `brand_exists`, read `brand_path` for tone; otherwise skip it.
4. For each video write down a one-sentence summary of what it teaches and the queries a developer
   would type to find it (repo name, tool, task, error messages, concepts).
5. Draft a sidecar per video using `config show` defaults and `references/seo-guide.md`.
   Series (numbered files) use `Topic | Series Name Ep. N`, the topic first (`references/seo-guide.md`). Write each draft to a scratch file
   **outside the project folder** (your scratchpad/temp directory, e.g. `<stem>.draft.yaml`) and
   run `lint` on it. Fix every error before the user sees it; keep the warnings to show them.
6. **Review gate.** Show every draft in one block: file, summary, lint warnings, then the YAML.
   Let the user approve, edit or reject each one. Re-lint edited drafts. Write nothing into the
   project folder before approval.
7. For each approved draft: `write-sidecar <folder>/<stem>.yaml --from <draft>`. It lints again,
   keeps an existing `video_id`, and refuses to change one. Report any refusal to the user.
8. If `discover` now says `fully_paired`, run `upload FOLDER` (no `--execute`: ytstudio's dry run)
   as a schema check and report problems. Never add `--execute` here.
9. Tell the user the next step: `/metatube:publish FOLDER` (mode from config).

### Walker source

1. `walker-status SOURCE`. On `repo name unknown`, ask the user once for the name Walker uses for the
   repo under its home (the folder under `~/.walker`) and re-run with `--repo NAME`. It's saved in
   `metatube.yaml`, so later runs don't need it.
2. Show the episode table: episode, status, chosen run and video path (`run.video`), newer render
   (`newer_run`), `video_id`, and any `warnings` (odd run ids). By status:
   - `ready`: rendered, not on YouTube yet → draft it.
   - `live`: has a `video_id` → leave it alone unless the user asks to redraft; then draft from the
     live run's `.srt` and keep its `video_id`. A `newer_run` is reported ("newer render, not on
     YouTube; the metadata stays tied to the live run") and otherwise ignored.
   - `not_rendered`: no video yet → skip it and say so.
   - `explainer_only`: only an old `explainer.mp4` render, which Studio can't tell apart from other
     episodes → hard stop for that episode until the user either re-renders it, or (if it's already on
     YouTube) pins that run in `metatube.yaml` (`episodes.<key>.pin_run: <run id>`) and gives its video
     id or URL. Then, in this order: re-run `walker-status`, draft, write the sidecar to
     `<run folder>/explainer.yaml`, and **straight away** `set-video-id <that sidecar> <id> --source SOURCE`,
     so the episode is `live` before publish. Never leave a pinned explainer episode `ready`: `match`
     can't pair it, and upload would send a second copy.
   - `live_run_missing`: `metatube.yaml` has a `video_id` but no run carries it → report it and skip the
     episode. MetaTube can't redraft or update it until a run folder holding that video's sidecar is back
     (the user restores Walker's home or re-creates the run).
   - `disagreement`: show `message` and skip the episode; publish's `walker-sync` step resolves it.
   An episode's `shorts` (any status) are its YouTube Shorts, in Walker's order: vertical cuts at
   `<run>/shorts/<stem>-short.mp4`, then `<stem>-short-2.mp4` … `-short-5.mp4`, each with its `number`, `hook`
   and `why` (from Walker's `short.yaml`). The user uploads each by hand as its own video; none goes in the
   playlist. Show each in the table (number, path, `video_id`, hook); `shorts: []` means the render made none.
3. Sources per episode: its `notes` (`story.md`, `screenplay.md`, plus the series `story.md`) and its
   `transcript` (the run's `.srt`, for chapters). `has_source` and `thin_sources` mean what they mean for
   a plain folder. Also read `series.yaml` (or `walker.yaml`): `series.title`, `project.name`,
   `project.repo_url` (link it in the description) and `project.walked_tag` (the version shown).
   Read `brand_path` if it exists.
4. Draft and lint each sidecar as in plain steps 4–5. Series titles: `Topic | <series.title> Ep. N`, with
   N = the episode's position in `episodes`; the topic is what the viewer gets, in the words they search for
   (the series `story.md` may list them). No previous/next episode links: the playlist links them.
   **Short sidecars** (one per Short in `shorts`; a live one only if the user asks): sources are that
   Short's own `.srt` (its `srt`), its `hook` and `why`, plus the episode's notes. Title: one hook-style line of
   60 chars or fewer naming the project, with the same searched words as its episode, ending ` #Shorts`; no
   `Ep. N`; an episode's Shorts never share a title (each comes from its own hook). Description: 1–3 sentences
   on the moment that Short shows, then `Full video: https://youtu.be/<id>` when the episode has a `video_id`
   (else the repo link only), the repo link, and 2–3 hashtags. No chapters: Shorts don't show them. Tags as
   for the episode.
5. **Playlist draft (series only).** If `walker-status` shows no `playlist`, draft one in a scratch YAML
   file with `title` (`series.title`), `description` (from the series `story.md`: what it covers, who
   it's for, the repo link) and `privacy` (`defaults.privacy` from `config show`). If a playlist is
   already recorded, show it and leave it: MetaTube never changes a created playlist's title or
   description.
6. **Review gate.** One block: every episode draft, then the playlist draft. Approve, edit or reject
   each. Write nothing before approval.
7. For each approved episode: `write-sidecar <run folder>/<stem>.yaml --from <draft>` (the path is
   `run.video` with `.yaml`); for each of its Shorts, that Short's `video` with `.yaml`. For the approved playlist: `playlist-draft SOURCE --from <draft>`.
8. Next step: `/metatube:publish SOURCE`.

## Workflow: publish

Mode = `--mode` argument, else `mode` from `config show`.

**Always first: `auth-check`.**
- `expired` → "Your Google login has expired (Testing-mode apps expire every 7 days)." Ask the user
  to run `! ytstudio login`, then re-run `auth-check`. Don't continue until `ok`.
- `not_initialized` / `not_installed` → send them to `/metatube:setup`.
- `api_disabled` → the YouTube Data API is off in the Cloud project. Give the link
  `https://console.cloud.google.com/apis/api/youtube.googleapis.com/overview?project=<gcp_project>`
  (from `config show`), ask them to click Enable, wait a few minutes, then re-run `auth-check`.
- `error` → show `detail` and stop.

Then `walker-status FOLDER`: a Walker source follows **Walker source** at the end of this workflow; a plain
folder follows the two modes below.

### Mode update (phase 1: videos uploaded by hand in Studio)

1. `quota FOLDER --mode update` → mention the estimate (50 units per video).
2. `match FOLDER`. Show a table: file → status, video title, id, privacy, upload date.
   - `matched`: ask the user to confirm.
   - `ambiguous`: show the candidates; ask which one.
   - `missing`: ask for the video URL or id (Studio → video → share link).
   For each confirmed choice run `set-video-id SIDECAR <id or url>`. `preset` ones already have it.
   `set-video-id` refuses an id another sidecar in the folder already holds; tell the user which.
   Studio titles new uploads from the file name with hyphens/underscores turned into spaces; the
   matcher allows for that.
   If a `preset` video was deleted from YouTube (`update` says "Video not found"), and the user has
   re-uploaded it, run `set-video-id SIDECAR <new id or url> --replace-deleted`. It only replaces
   the old id after YouTube confirms the old video is gone.
3. For each sidecar with a `video_id`, run `update SIDECAR` (dry run) and show **current vs. new**
   title, description and tags side by side. Take "current" from the `match` candidate with that
   id (`title`, `description`, `tags`); ytstudio's own dry run only prints the new title and
   "description: (updated)". If the video isn't among the candidates (older than the last 50
   uploads), say the current description isn't available and show only the new one.
4. Ask explicitly: "Apply these changes?" Only on yes: `update SIDECAR --execute` for each.
5. Report: updated (with `studio_url`), failed (with output). Then list what MetaTube can't set on
   existing videos and the sidecar's intended values — **category, language, made-for-kids,
   visibility** — for the user to set in Studio.
6. Re-running update on a video is fine; always dry-run and ask again.

### Mode upload (phase 2: after the audit passes)

1. If `config show` has `audit_passed: false`, warn first: "Your project hasn't passed the YouTube
   API audit, so these uploads will be locked private and can't be made public." Continue only if
   the user still wants to.
2. `quota FOLDER --mode upload`. If `over_safe_daily`, warn (~6 uploads/day on the default quota)
   and propose `--max 6`.
3. `upload FOLDER [--max N]` (dry run). Show the plan: `mode` (folder or per_file), `pending`,
   `skipped_live`, `not_ready` (videos without a sidecar - run generate first), and ytstudio's output.
   **If `possible_duplicates` is not empty, stop:** those files have a video with the same name on
   the channel already (probably uploaded in Studio during phase 1). Ask the user, video by video,
   whether it's the same video; if yes, `set-video-id` it (then it's skipped, and
   `/metatube:publish --mode update` applies the metadata) and re-run the dry run. If
   `duplicate_check_error` is set, tell the user the check couldn't run and ask before going on.
4. Ask explicitly: "Upload these N videos?" Only on yes: `upload FOLDER --execute [--max N]`.
5. Report from `now_live` (with `https://youtu.be/<id>` from each sidecar), the results' output, and
   the quota estimate.
   - Output mentions quota → it resets at midnight Pacific; running the same command again resumes.
   - A `youtu.be/<id>` appears in output for a file not in `now_live` → the write-back failed. Tell
     the user, and with their OK run `set-video-id` for it so it isn't uploaded twice.
   - If `audit_passed` is false, repeat that the uploads are locked private.

### Walker source

Every write below shows a dry run first and runs with `--execute` only after the user's yes. The user may
say yes to the metadata updates and the playlist together, once they've seen both dry runs.

1. **Episodes.** Show the `walker-status` episode table (as in generate). Episodes that aren't `ready` or
   `live` are skipped, with the reason.
2. **Quota.** `quota SOURCE --mode <mode>` → mention the estimate, including `playlist_creates` and
   `playlist_adds` (50 units each). Upload mode with `over_safe_daily` → propose fewer episodes this run.
3. **Mode update.**
   1. `match SOURCE` pairs episodes without a `video_id` with the channel's videos (Studio titles a hand
      upload from Walker's file name, e.g. `<series name>-<episode>`). Confirm each as for a plain folder,
      then `set-video-id <sidecar> <id or url> --source SOURCE`. `--source` makes it refuse an id another
      episode, or another Short (of any episode, or this episode's other Shorts), already holds. `match`
      lists every Short too (Studio titles them `<stem> short`, `<stem> short 2`, …).
   2. `walker-sync SOURCE` copies the ids into `metatube.yaml`. `synced: false` → show `conflicts` and
      `disagreements` and stop. The sidecar wins: if the sidecar's id is the right one, the user deletes
      (or corrects) `episodes.<key>.video_id` in `metatube.yaml` by hand and you re-run `walker-sync`. If
      the sidecar's id is wrong, it changes only through `set-video-id --replace-deleted`. Two runs with
      different ids: the user decides which video is real; don't guess.
   3. `update <sidecar>` per live episode, and per Short (every one in `shorts`) with a sidecar and
      `video_id`, exactly as plain update steps 3–5. `walker-sync` doesn't track Shorts: their sidecars
      hold their ids.
4. **Mode upload.** Shorts are never uploaded by MetaTube; use update mode for them. Audit warning as in plain upload step 1. For each `ready` episode with a sidecar:
   `upload <run folder>` (dry run; never for a `live` episode), handle `possible_duplicates` as for a plain
   folder, and on yes `upload <run folder> --execute`. Then `walker-sync SOURCE`.
5. **Playlist (series only; skip it for a single Walker video).** No playlist draft → send the user to
   `/metatube:generate`. Otherwise `playlist SOURCE` (dry run): show `create` (title, description,
   privacy) if the playlist is new, and `adds` (episode → position).
   - `collision`: the channel already has a playlist with this title and `metatube.yaml` has no id. Show
     each one's `items`, with its `flagged` items, next to the series' episodes, and ask whether it is
     this series' playlist (for example one the user made by hand).
     - Yes → `playlist-adopt SOURCE <id>`; only after the user's yes with the flagged list in view,
       `playlist-adopt SOURCE <id> --confirm`. Then re-run `playlist SOURCE`.
     - A different playlist → `playlist SOURCE --create-new` (dry run).
   - On yes: `playlist SOURCE --execute`, plus `--create-new` if the dry run used it (the flag isn't
     remembered; without it the collision comes back). Report `added` and `not_added` (with output).
   - A create that printed no id (the error says so): don't re-run it. Ask the user to find the playlist
     in Studio, then `playlist-adopt` it.
   - MetaTube only adds episodes, in `series.yaml` order, and never adds one twice. It doesn't rename,
     reorder or remove anything; the user does that in Studio.
6. **Report** per episode: updated or uploaded, in the playlist or not, and what still needs Studio
   (category, language, made-for-kids, visibility). Then the Studio steps MetaTube can't do, per video:
   - every Short's **Related video** set to its episode (Studio → the Short → Related video), the only link a
     Shorts viewer can tap; list them per episode (Short 1, Short 2, …) so none is missed;
   - not yet public: schedule one episode a day, its Short 1 the same day and each further Short a day after
     the one before, so every Short gets its own day (Studio's Schedule; `publish_at` works only for API
     uploads, locked private until the audit passes).
