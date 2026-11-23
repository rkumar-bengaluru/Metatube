# Several Shorts per episode: design

Date: 2026-11-23. Status: approved by rupak.k ("go ahead", 2026-11-23). Follows Walker 0.15.0, whose `walker render`
makes up to `project.shorts` (0 to 5) Shorts per video (Walker spec `docs/design/specs/2026-11-23-several-shorts-design.md`).

## Why

Walker now writes, in a run's `shorts/` folder, `<stem>-short.mp4` and then `<stem>-short-2.mp4` … `<stem>-short-5.mp4`
(each with its `.srt`), and one `short.yaml` listing them in the same order (`shorts[k-1]` is Short k, with its
`title`, `hook` and `why`). MetaTube finds only `<stem>-short.mp4` and the skill drafts one Short sidecar, so the other
Shorts get no metadata and no Related-video step. Each Short links to its episode; none goes in a playlist.

## Approaches

- **A list replaces the one Short (picked).** `EpisodeState.shorts: list[ShortVideo]`, in Walker's order; every place
  that handled `short` loops over the list. One code path; a run with only `<stem>-short.mp4` is a list of one.
- Keep `short` and add `extra_shorts`: two paths for the same thing, and every consumer must remember both. Rejected.

## Design

- `walker.py`: `ShortVideo(RunVideo)` adds `number: int` (1 to 5), `title`, `hook`, `why` (`str | None`) and
  `missing: bool`. `find_shorts(root, stem) -> (list[ShortVideo], warnings)`: per run, the files `<stem>-short.mp4` (number 1) and
  `<stem>-short-k.mp4` (k 2 to 5) that exist, in number order, each with its hook and why from that run's
  `short.yaml` entry k-1 (missing or unreadable → None). The run chosen: the newest run with a Short holding a
  `video_id` (any number), else the newest run with any Short; its Shorts are returned. `find_short` goes.
  A Short whose `.mp4` Walker removed (a failed rebuild) but whose sidecar holds a `video_id` stays, `missing:
  true`, so its id is still guarded and it still picks its run. Warnings (into the episode's `warnings`): a newer
  run with Shorts than the live one shown, two runs with live Shorts, a missing Short. (From the architect review.)
- `episodes.py`: `EpisodeState.shorts: list[ShortVideo]` (default empty) replaces `short`; `walker_entries` includes
  every Short.
- `cli.py`: `_source_holders` checks every Short (named `<key> (Short k)`); `quota`'s `shorts` counts every Short
  with a sidecar and a `video_id` (the ones publish updates).
- `SKILL.md`: the episode table shows each Short (number, path, `video_id`, hook); a sidecar per Short (the Short's
  `video` with `.yaml`), from that Short's `.srt`, `hook` and `why`; titles differ between one episode's Shorts;
  publish updates each Short with a sidecar and id; the Studio checklist sets every Short's Related video to its
  episode and schedules the Shorts on following days, one a day after the episode's. `match` lists every Short.
- Version 0.3.3 → 0.4.0 (helper `pyproject.toml`, `.claude-plugin/plugin.json`, marketplace if it carries one).

## Non-goals

No uploading of Shorts (still by hand), no playlist change, no change to Walker. Left as before: the Shorts' run
is chosen on its own, not tied to the episode's `run` or `pin_run` (a pinned explainer's Shorts are not found), and
a Short rebuilt in place keeps its old sidecar.

## Testing

`find_shorts`: one, three, a gap (1 and 3), the hook/why per number, a missing or broken `short.yaml`, the live run
wins over a newer one, none. `walker-status` JSON carries `shorts`. `_source_holders` refuses an id held by Short 2.
`quota` counts the Shorts with an id. A missing live Short is kept and guarded. `walker_entries` lists all.
