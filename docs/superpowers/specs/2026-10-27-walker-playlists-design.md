# MetaTube: Walker series, playlists and blank captions

Date: 2026-10-27. Status: draft for review.

## Why

The owner makes training videos with Walker (`C:\2026\rkumar\Walker`), mostly as a series: several episodes
that follow one repo's learning path. MetaTube v1 expects a flat folder where each video sits next to its notes
and transcript with the same stem. Walker splits these apart: what a video is written from lives in one folder,
and the rendered video lives in another, a new folder per render. A series should also land on YouTube as a
playlist, which v1 doesn't do (it was a v1 non-goal).

The owner also found that YouTube's automatic captions show on top of the captions Walker burns into every video.
They fixed their first video (a standalone test, not part of any series, so nothing needs to be carried
over into a manifest) by hand in Studio (Subtitles → English track → put a single `.` → Publish; an
empty track would not publish). MetaTube should do this for them.

## Goals

1. **Walker source folders as input.** `/metatube:generate` and `/metatube:publish` accept a Walker series
   folder, or a single (non-series) Walker folder, and find each video's rendered file on their own.
2. **One playlist per Walker series.** Each series gets its own new playlist, holding its episodes in series
   order. A single Walker video gets none.
3. **Blank captions.** After a video has a `video_id`, MetaTube publishes a caption track holding one `.` cue, so
   viewers who turn on CC see only the burned-in text.
4. **Re-renders only update metadata.** A video that already has a `video_id` is never uploaded again. A new
   render of an episode only carries the metadata forward and, if asked, updates title, description and tags.
5. Plain folders (v1's layout) work exactly as today.

## Non-goals

- Re-uploading or replacing a video after a re-render.
- Adding videos to a playlist MetaTube didn't create for that series.
- Playlists for plain v1 folders.
- Uploading Walker's real `.srt` as captions, or changing Walker to stop burning captions in. (Possible later:
  better for accessibility, translation and search. Not now.)
- Importing Walker's code or requiring the `walker` command to be installed.
- Changing Walker.

## Anti-goals (failure even if it "works")

- A second playlist for a series that already has one.
- A video uploaded twice.
- MetaTube reading, printing or copying OAuth tokens or client secrets.
- Any write to YouTube (update, playlist, captions) without a dry run shown first and the owner's yes in this
  session.

## Constraints

- ytstudio-cli is pinned at 0.4.2. It has `playlists` commands (`list`, `show`, `create`, `update`, `add`,
  `items`, `reorder`, ...) but no captions command.
- Phase 1 still applies: the Cloud project hasn't passed the YouTube API audit, so the default publish mode is
  `update` (owner uploads in Studio, MetaTube applies metadata). When uploading by hand, the owner keeps Walker's
  file name, so Studio's title is the file stem and v1's `match` pairs it (it already allows for hyphens turned
  into spaces).
- Sidecars may only hold the keys in `references/sidecar-schema.md` (ytstudio rejects others). Anything else
  MetaTube needs to remember goes in a separate file.
- Windows is the main platform.

## What Walker gives us

Verified against Walker at `df59e7c` (`skills/walker-series/SKILL.md`, `src/walker/render/run.py`,
`examples/cube/series/`).

**Source side** (what the video is written from, can be committed):

- Series folder: `<repo>/.walker/series/<name>/` when the owner owns the repo, otherwise outside the clone,
  e.g. `~/walkers/<repo>/series/<name>/`.
  - `series.yaml`: `series.name` (slug), `series.title`, `episodes` (folder names, in order), `project`
    (`name`, `repo_url`, `walked_tag`, `audience`, ...).
  - `story.md`: the series' audience, a table of episodes, how they connect, what's left out.
  - One folder per episode (`ep1-first-cube/`): `story.md`, `screenplay.md`, `walker.yaml`, `takes/`.
- Single Walker folder: `<repo>/.walker/` (or outside the clone): `walker.yaml`, `story.md`, `screenplay.md`.

**Output side** (the rendered video, under the owner's home, not committed):

- Episode: `~/.walker/<repo>/series/<name>/<episode>/video/<run id>/<name>-<episode>.mp4`, plus
  `<name>-<episode>.srt`, `cost.json`, and other CodeCast output.
- Single video: `~/.walker/<repo>/video/<run id>/<repo>-<walked_tag>.mp4` (`<repo>.mp4` with no tag), plus `.srt`.
- Every render makes a new `<run id>` folder (timestamp-like, e.g. `20261027-152921`).
- `walker render` replaces non `[A-Za-z0-9._-]` characters in the stem with `-`.
- Renders made before Walker `c8aeafa` are named `explainer.mp4`.
- Walker's video is ready to upload as-is, with captions burned in.

## The design

### 1. Detecting a Walker folder

`discover` (or a new subcommand, builder's choice) recognises:

- a **series** folder: contains `series.yaml` with `format: walker/...` and a `series` block;
- a **single Walker** folder: contains `walker.yaml` with `format: walker/...` and is not inside a series;
- anything else is a plain v1 folder and goes through the existing code unchanged.

Pointing MetaTube at an episode folder inside a series should say "point me at the series folder" rather than
treat it as a single video.

### 2. Finding the video

For each episode (series) or the one video (single), MetaTube looks under Walker's home `video/` folder:

1. **Candidates** are the run folders that hold a video with the **expected stem** (`<name>-<episode>`, or
   `<repo>-<tag>` / `<repo>`, sanitised as Walker does). Folders without it (other files, odd names, failed
   renders) are ignored, so the choice doesn't depend on the run id format.
2. One candidate → that's the run. Several → the newest: by run id when every candidate's name is Walker's
   timestamp form (`YYYYMMDD-HHMMSS`), otherwise by the video file's modification time.
3. The chosen run (id and video path) is always shown in the generate table, so the owner sees it before
   anything is drafted.

**`explainer.mp4` is a hard stop.** Renders made before Walker `c8aeafa` are all named `explainer`, so Studio
titles them all `explainer` and `match` can't tell episodes apart. Such a run is never a candidate on its own:
MetaTube reports it and drafts that episode only if the owner either re-renders it or gives its video id (or
URL) by hand, which is recorded with `set-video-id`.

`<repo>` is the name Walker uses for its home folder. For `<repo>/.walker/...` it is the repo folder's name. For
a source folder outside the clone the builder must check how Walker names the home (`Workspace` in Walker's
`src/walker/`) and match it; if it can't be worked out from the source folder, ask the owner once and remember
the answer in the manifest (§4).

An episode with no rendered video yet is reported as `not rendered` and skipped. It isn't an error.

This choice applies only to videos not yet on YouTube; a live video stays tied to its live run (§5).
The owner can pin an episode to a specific run in the manifest.

### 3. Sources for the draft

Per episode, the "notes" are its `story.md` and `screenplay.md`, plus the series `story.md` for context. The
transcript is the `.srt` beside the chosen video, used for chapters as v1 does. From `series.yaml`:
`series.title` (series name in titles: `Series Title Ep. N: Topic`, N = position in `episodes`), `project.name`,
`project.repo_url` (linked in descriptions), `project.walked_tag` (the version the video shows). v1's `has_source`
and thin-source checks apply to these files. No previous/next episode links in descriptions: in update mode
the ids only exist after publish, and going back to rewrite approved sidecars costs a review and an update per
episode. The playlist does that job. (My call.)

Single Walker video: its `story.md`, `screenplay.md`, `walker.yaml` `project`, and its `.srt`.

### 4. Where things are written

- **Sidecar**: next to the video, `<stem>.yaml` in the run folder. That's where ytstudio's upload expects it,
  and v1's `update`/`set-video-id` work on it unchanged.
- **Manifest**: `metatube.yaml` in the Walker source folder (series folder or single Walker folder), so it
  survives re-renders and can be committed. It records, per episode: the run id used, the sidecar path, the
  `video_id`, and whether the blank caption is done; for a series also the playlist id, title and description,
  and which videos have been added. The exact shape is the builder's.
- **Which one wins**: the sidecar is the source of truth for the `video_id`, because ytstudio and v1's
  `update`/`set-video-id` read it. The manifest is MetaTube's bookkeeping: it copies the id from the sidecar,
  never the other way. MetaTube never writes a manifest id into a sidecar. If the two disagree, stop, show both,
  and ask; the only fix MetaTube offers is updating the manifest from the sidecar. Changing a sidecar's id stays
  with v1's `set-video-id` rules (`--replace-deleted` only).

### 5. Re-renders

The owner confirmed: once a video is on YouTube, the old cut always stays there. Nobody swaps it in Studio.

- **Live episode (has a `video_id`)**: its run is fixed. The manifest's run id is the **live run**, the one
  actually on YouTube. Its sidecar stays in that run folder, and every redraft takes chapters from that run's
  `.srt`, never from a newer one, whose timings would be wrong for the live video. A newer render is reported
  ("ep2 has a newer render, not on YouTube; metadata stays tied to the live run") and otherwise ignored.
  The owner can still ask to regenerate the draft, for example when `story.md` or `screenplay.md` changed.
  Publishing then only runs `update`. Never upload.
- **Not live yet**: the run chosen by §2, and it's treated as a new video (draft, review, write sidecar).
- **Live run folder missing** (the owner deleted Walker's home): the manifest still has the `video_id`. Report
  it, and don't redraft that episode until the owner points at a folder or says to draft without chapters.

### 6. Playlist (series only)

- Title: `series.title`. Description: drafted from the series `story.md` (what the series covers, who it's for,
  the repo link), shown in the same review gate as the episode drafts, and linted for YouTube's limits.
- Privacy: the config default visibility (`public` by default). (My call; the owner can change it in the draft.)
  Note: while uploads are hand-made, the episodes' own privacy is whatever the owner set in Studio.
- Created once. The manifest's playlist id is the only playlist MetaTube ever adds to. If the manifest has no id
  but the channel already has a playlist with the same title (`ytstudio playlists list`), stop and ask whether
  it's this series' playlist or a different one. This guards against duplicates after a lost manifest.
  Before recording it as this series' playlist, list its items (`ytstudio playlists items`) and show them next to
  the series' episodes. Flag every item that isn't one of this series' known `video_id`s or whose title doesn't
  carry the series title. If any are flagged, ask again with that list in view. "Different one" → create a new
  playlist.
- Episodes are added in `series.yaml` order once they have a `video_id`. An episode published later is inserted
  at its series position, so the playlist order always matches `episodes`. Videos already in the playlist
  (`ytstudio playlists items`) are not added again.
- After creation, MetaTube only adds episodes. It doesn't change the playlist's title or description, reorder
  it, or remove items; the owner does that in Studio. (My call.)
- Publish order: update metadata, then playlist, then captions. Each has its own dry run and its own yes;
  the owner can say yes to all three at once after seeing all three dry runs.
- ytstudio 0.4.2: `playlists create --title --description --privacy [--language] --execute` prints
  `Created: <title> (<id>)` (no JSON); `playlists add <id> --video <vid> [--position N] --execute`. The builder
  verifies the exact output and JSON options of `list`, `items`, `create`, `add` against the installed 0.4.2 and
  adds them to `references/cli-contract.md` before using them, as for v1.

### 7. Blank captions

- For each video with a `video_id` and the setting on: list its caption tracks. If a non-automatic track already
  exists (e.g. the owner did it by hand, as on the first video), skip it. Otherwise insert an English track (the
  sidecar's `default_language`) holding one SRT cue whose text is `.`, from `00:00:00,000` to `00:00:01,000`
  (timing is my call). Studio rejected an empty track; whether the API accepts an empty file is unknown and not
  needed.
- ytstudio has no captions command, so the helper does this by running a small MetaTube script **with
  ytstudio's own Python interpreter** (in ytstudio's uv tool environment), calling
  `ytstudio.services.get_data_service()` and the API's `captions().list` / `captions().insert`. The login stays
  inside ytstudio's code; MetaTube never opens the token file. `SKILL.md`'s "you never call the YouTube API
  yourself" rule gets this one stated exception. The script is pinned to ytstudio 0.4.2 like the rest of the
  contract.
- Dry run by default: show which videos would get the track and which are skipped (and why); `--execute` only
  after the owner's yes.
- Setting: `blank_captions` is stored in MetaTube's config (`config set blank_captions walker|always|never`),
  not just inferred, so the owner can turn it off for good. Default `walker`: on for Walker sources (their
  captions are always burned in), off for plain folders. `config show` and `/metatube:setup` show it.
- **The spike is blocking for this section.** Before any of §7 is built, on one test video, prove both:
  1. `captions.insert` with the one-cue file succeeds with the scopes ytstudio already asks for
     (`youtube.force-ssl`), with no new consent; and
  2. the watch page then shows only the burned-in text with CC on, i.e. the `.` track replaces the automatic
     one.

  If (1) needs a scope ytstudio doesn't request, the captions feature is blocked: MetaTube can't change
  ytstudio's scopes, and the owner would have to re-consent through some other route. If (2) fails, the
  approach is wrong. Either way, stop and come back to the owner. §1–§6 don't depend on the spike and can be
  built and shipped without §7.

### 8. Quota (approximate, per the YouTube API's published costs)

- Per episode: `videos update` 50, captions list 50, captions insert 400, playlist add 50 (about 550).
- Per series: playlist create 50, playlist list/items a few units.
- A 5-episode series is about 2,800 units against a 10,000/day default. `quota` reports this before publishing.

## Workflow changes (SKILL.md)

- **generate**: Walker folder detected → show the episode table (episode, chosen run and video path, or
  not rendered / `explainer` stop, live run and `video_id` for live episodes, newer render not on YouTube) → drafts for episodes that need one, plus the playlist draft → one
  review gate → write sidecars and the manifest.
- **publish (update mode)**: `match` as today for episodes without a `video_id` (Studio title = Walker's file
  stem) → metadata update → playlist → blank captions, each with dry run and yes. Report what's done per episode
  and what still needs Studio (category, language, made-for-kids, visibility, as today).
- **publish (upload mode)**: as today, per episode; never for one with a `video_id`; then playlist and captions.

## Testing

- Unit tests with a fake Walker home in `tmp_path`: series and single layouts, run choice (expected stem,
  timestamp ids, non-timestamp ids by mtime, stray folders), pinned run, not-rendered episode, `explainer.mp4`
  hard stop, stem sanitising, re-render carry-over, manifest/sidecar
  disagreement.
- Playlist logic with ytstudio calls faked: create once, reuse from manifest, same-title prompt with unrelated
  items flagged, order and
  insert positions, no duplicates.
- Captions (after the spike passes): skip when a manual track exists, dry-run output, the one-cue SRT content,
  the `walker|always|never` setting.
- Manifest/sidecar: disagreement stops, the manifest never writes a sidecar id.
- An `examples/walker-series/` fixture (source side plus a fake home with empty `.mp4` files), like v1's examples.

## Left to the builder

Manifest schema; helper subcommand names and JSON shapes; how the run id is sorted if Walker's format varies;
how to find ytstudio's interpreter on Windows and macOS/Linux (`uv tool dir`); parsing ytstudio's text output;
README and roadmap updates.
