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
  - Bash(ytstudio status*)
  - Bash(ytstudio --version)
  - Bash(ytstudio profile brand show*)
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
and apply it through **ytstudio-cli 0.4.2** (the base tool). You never call the YouTube API
yourself. The audience is developers learning about GitHub repos.

## The helper

Deterministic work goes through `metatube-helper`, which lives next to this file. Run it as:

```
uv run --project "<this skill's base directory>/helper" metatube-helper <subcommand> ...
```

(The base directory is shown when this skill loads.) Every subcommand prints one JSON object.
Subcommands: `discover FOLDER`, `lint PATH`, `write-sidecar SIDECAR --from DRAFT`, `auth-check`,
`match FOLDER [--limit N]`, `set-video-id SIDECAR REF`, `update SIDECAR [--execute]`,
`upload FOLDER [--execute] [--max N]`, `quota FOLDER --mode update|upload`, `config show`,
`config set KEY VALUE`, `secrets-present`.

Read-only subcommands run without a prompt. Writes and anything with `--execute` ask the user
for permission each time; that prompt is part of the safety design, so don't ask the user to
pre-approve them.

Never run `ytstudio videos update` or `ytstudio videos upload` yourself: use the helper, which
passes long descriptions safely and forces UTF-8. Never write or edit a sidecar (`*.yaml` next to
a video) with the Write or Edit tool: write drafts elsewhere and use `write-sidecar`, which lints
the draft and refuses to change or drop a `video_id`. Raw `ytstudio` is fine for `status`, `init`,
`login` (user runs it), `profile brand show|edit|set`, `videos categories`.

References (read when the step needs them): `references/cli-contract.md`,
`references/sidecar-schema.md`, `references/seo-guide.md`, `references/setup-console-steps.md`,
`references/audit-guide.md`.

## Guardrails (always)

- Never `--execute` (update or upload) without the user's explicit yes **in this session**, given
  after they saw the dry run.
- Never change or remove an existing `video_id`; never upload a sidecar that has one.
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
   `ytstudio --version`. If ytstudio is missing or not 0.4.2, ask, then run
   `uv tool install ytstudio-cli==0.4.2` (add `--force` when replacing another version).
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
   apply changes with `config set defaults.<key> <value>`. Check `ytstudio profile brand show`; if
   unset, offer to create one (`ytstudio profile brand edit`, or write a file and
   `ytstudio profile brand set --file <file>`).
8. **Audit.** Ask whether the Cloud project has passed the YouTube API compliance audit.
   Save `config set audit_passed true|false`. If false, explain: API uploads are locked private until
   it passes, so for now upload in Studio and use `/metatube:publish --mode update`. Then walk them
   through `references/audit-guide.md`. You never submit the form.
9. **Summary.** `config show` → one screen: channel, profile, ytstudio version, defaults, mode, and
   "your login expires every 7 days in Testing mode; MetaTube will tell you when to re-login".

## Workflow: generate

1. `discover FOLDER`. Report `unsupported` files (not uploadable by ytstudio) and `orphan_sidecars`.
   No videos → ask where the videos are; don't guess.
2. Partition:
   - `live: true` → list them and leave them alone, unless the user explicitly asks to revise one;
     then keep its `video_id` exactly.
   - existing sidecar, not live → ask: regenerate or keep?
   - `has_source: false` → refuse to draft that video and say which files you looked for
     (`<stem>.md/.txt`, `<stem>.srt/.vtt`, `<stem>.pdf/.pptx`).
   - `sidecar_error` set → show it; ask before overwriting.
3. Read the sources: notes, transcripts, slides (text where readable), the folder README, and the
   public README of any GitHub repo URL in the notes if you can reach it (no cloning).
   `ytstudio profile brand show` for tone (skip if unset).
4. For each video write down a one-sentence summary of what it teaches and the queries a developer
   would type to find it (repo name, tool, task, error messages, concepts).
5. Draft a sidecar per video using `config show` defaults and `references/seo-guide.md`.
   Series (numbered files) use `Series Name Ep. N: Topic`. Write each draft to a scratch file
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

## Workflow: publish

Mode = `--mode` argument, else `mode` from `config show`.

**Always first: `auth-check`.**
- `expired` → "Your Google login has expired (Testing-mode apps expire every 7 days)." Ask the user
  to run `! ytstudio login`, then re-run `auth-check`. Don't continue until `ok`.
- `not_initialized` / `not_installed` → send them to `/metatube:setup`.
- `error` → show `detail` and stop.

### Mode update (phase 1: videos uploaded by hand in Studio)

1. `quota FOLDER --mode update` → mention the estimate (50 units per video).
2. `match FOLDER`. Show a table: file → status, video title, id, privacy, upload date.
   - `matched`: ask the user to confirm.
   - `ambiguous`: show the candidates; ask which one.
   - `missing`: ask for the video URL or id (Studio → video → share link).
   For each confirmed choice run `set-video-id SIDECAR <id or url>`. `preset` ones already have it.
   `set-video-id` refuses an id another sidecar in the folder already holds; tell the user which.
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
