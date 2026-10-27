# ytstudio-cli contract (pinned 0.4.2)

Verified against the installed ytstudio-cli 0.4.2 from PyPI. Re-verify everything here before
bumping the pin, against the released package, not the GitHub main branch (main has unreleased
commands such as `profile brand`).

## Install and auth

- `uv tool install ytstudio-cli==0.4.2` (Python >= 3.12). Works on Windows.
- `ytstudio init --client-secrets <path>` copies the OAuth client to
  `~/.config/ytstudio-cli/client_secrets.json`. MetaTube only checks that this file exists.
- `ytstudio login` runs a local OAuth server on port 9876 and opens the browser (one consent).
  `--headless` prints a URL and asks for the failed 127.0.0.1 redirect URL instead.
- Scopes: `youtube.readonly`, `youtube.force-ssl` (covers uploads and updates), YouTube Analytics
  read scopes.
- Profiles: one per channel. `YTSTUDIO_PROFILE=<name>` overrides the active profile per command.
- **`ytstudio status` exits 0 even when not authenticated or expired.** Don't use it as an auth
  check. Use `ytstudio videos list -n 1 -o json`, which exits 1 ("Session expired or revoked ...
  Run ytstudio login") on an expired token. The helper's `auth-check` does this.

## Reading

- `ytstudio videos list -n N -o json` returns `{"videos": [{id, title, description,
  published_at, privacy, tags, category_id, ...}], "next_page_token", "total_results"}`
  (1 unit). It lists the channel's uploads playlist, including private videos.
- `ytstudio videos categories` lists category ids.
- `ytstudio videos show -o json -- <id>` prints one video; "Video not found: <id>" and exit 1 when
  it was deleted.
- No `profile brand` command in 0.4.2. MetaTube keeps its own optional `brand.md` next to its config.

## Updating (phase 1)

- `ytstudio videos update <id> [--title T] [--description D] [--tags "a,b,c"] [--execute]`
- Dry run by default. **Only title, description and tags**, not category, language, privacy or
  made-for-kids. Tags are split on commas, so a tag may not contain one. About 50 units.

## Uploading (phase 2)

- `ytstudio videos upload <file|folder> [--execute] [--max N]`. Dry run by default.
- Videos: `.mp4 .mov .mkv .webm`. Sidecar: same basename `.yaml` (required). Thumbnail: same
  basename `.jpg`/`.png` up to 2 MB; near-miss extensions (`.jpeg`, `.webp`, ...) fail fast.
- A folder fails as a whole if any video lacks a sidecar or any sidecar lacks a video. The helper
  then uploads file by file.
- After each success it writes `video_id` and `uploaded_at` into the sidecar; re-runs skip those.
  If the write-back fails it prints the id (`ok <file> -> https://youtu.be/<id>`) so it can be
  added by hand.
- On `quotaExceeded` it stops cleanly and exits non-zero. About 1600 units per upload.
- Sidecars are read with `Path.read_text()` (no explicit encoding), so the helper sets
  `PYTHONUTF8=1` to make UTF-8 descriptions work on Windows.
- Uploads from a Cloud project that hasn't passed the YouTube API compliance audit are locked
  private.
