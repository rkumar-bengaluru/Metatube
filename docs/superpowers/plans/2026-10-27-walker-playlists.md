# Walker series, playlists and blank captions — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** MetaTube reads a Walker series (or single Walker) source folder, finds each rendered video in Walker's
home, drafts and publishes metadata as v1 does, puts a series into its own playlist, and adds a one-cue `.`
caption track that hides YouTube's automatic captions.

**Architecture:** New helper modules: `walker.py` (layout, run choice), `manifest.py` (`metatube.yaml`
bookkeeping), `episodes.py` (per-episode state), `playlists.py` (pure playlist planning), `captions.py`
(caption planning), plus `yt_captions.py`, a standalone script run by ytstudio's own Python. Each run folder in
Walker's home is a flat v1 folder (`<stem>.mp4`, `<stem>.srt`, `<stem>.yaml`), so v1's `discover`, `update`,
`set-video-id` and `write-sidecar` work on it unchanged; the new code only finds the right run folder and does
the bookkeeping across episodes.

**Tech Stack:** Python ≥ 3.12, ruamel.yaml, pydantic, pytest, ytstudio-cli 0.4.2 (subprocess), uv.

**Spec:** `docs/superpowers/specs/2026-10-27-walker-playlists-design.md`

## Global Constraints

- All work on branch `feat/playlist-support`. Commit messages end with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Helper lives in `skills/metatube/helper/`; run tests from there with `uv run pytest -q`. All 102 existing
  tests keep passing.
- ytstudio-cli pinned at 0.4.2; always called through `ytstudio.run_ytstudio` (argv list, UTF-8, profile env).
- Every helper subcommand prints exactly one JSON object (`cli._emit` / `cli._error`).
- Nothing writes to YouTube without `--execute`; the default is a dry run.
- Sidecars hold only `schema.ALLOWED_KEYS`; all other bookkeeping goes in `metatube.yaml`.
- The sidecar is the source of truth for `video_id`; the manifest copies from it and never writes into it.
- MetaTube never opens ytstudio's token or client-secret files (captions go through `ytstudio.services`).
- Walker home: `$WALKER_HOME`, else `home:` in `<~/.walker>/config.yaml`, else `~/.walker`.
- Video stem sanitising, as Walker: `re.sub(r"[^A-Za-z0-9._-]+", "-", stem)`.
- Run ids: Walker's `%Y%m%d-%H%M%S` (e.g. `20261027-152921`).
- Caption cue, exact: `1\n00:00:00,000 --> 00:00:01,000\n.\n`.
- Quota units: update 50, playlist create 50, playlist add 50, captions list 50, captions insert 400.
- §7 (captions) is built only after the Task 6 spike passes. Tasks 1–5 and 8 don't depend on it.

## Review Focus

1. `series.name` in `series.yaml` differs from the series folder's name → Walker's home uses `series.name`;
   so must MetaTube (test in Task 1).
2. An episode listed in `series.yaml` whose folder or render doesn't exist → `not_rendered`, never a crash
   (test in Task 3).
3. Two run folders of one episode both hold a sidecar with a `video_id` (different or same) → if different,
   `disagreement` and stop; if same, the newest such run is the live run (test in Task 3).
4. `ytstudio playlists add` prints `Done: 0 added, 1 failed` and still exits 0 → the helper re-reads the
   playlist items and reports the video as not added (test in Task 5).
5. Non-ASCII series titles and descriptions (`—`, `é`) round-trip through `metatube.yaml` on Windows
   (test in Task 2).

---

### Task 1: Walker layout and run choice

**Files:**
- Create: `skills/metatube/helper/src/metatube_helper/walker.py`
- Test: `skills/metatube/helper/tests/test_walker.py`

**Interfaces:**
- Produces:
  - `RUN_ID = re.compile(r"^\d{8}-\d{6}$")`
  - `@dataclass WalkerSource: kind: Literal["series", "single"]; folder: Path; title: str; series_name: str | None; episodes: list[str]; project: dict; repo_name: str | None`
  - `detect(folder: Path) -> Literal["series", "single", "episode", "plain"]` — `series`: `series.yaml` with `format` starting `walker/` and a `series` mapping; `episode`: `walker.yaml` whose parent has such a `series.yaml` listing this folder name; `single`: other `walker.yaml` with `format: walker/...`; else `plain`.
  - `load_source(folder: Path, repo_name: str | None = None) -> WalkerSource` — `title`: `series.title` (series) or `project.title`/`project.name` (single). `repo_name`: the argument if given; else for `<x>/.walker/series/<name>/` and `<x>/.walker/` it's `x.name`; else `None`.
  - `walker_home() -> Path`
  - `sanitize(stem: str) -> str`
  - `expected_stem(src: WalkerSource, episode: str | None) -> str` — series: `sanitize(f"{series_name}-{episode}")`; single: `sanitize(f"{repo_name}-{walked_tag}")`, or `sanitize(repo_name)` with no tag.
  - `video_root(src: WalkerSource, episode: str | None) -> Path` — series: `walker_home()/repo_name/"series"/series_name/episode/"video"`; single: `walker_home()/repo_name/"video"`. Raises `ValueError("repo name unknown")` when `repo_name` is None.
  - `@dataclass RunVideo: run_id: str; folder: Path; video: Path; srt: Path | None; sidecar: Path | None; video_id: str | None; mtime: float`
  - `find_runs(root: Path, stem: str) -> tuple[list[RunVideo], list[Path]]` — run folders with `<stem>.mp4` (candidates, `video_id` read from `<stem>.yaml` if present) and the run folders holding only `explainer.mp4`. A missing `root` gives `([], [])`.
  - `choose_run(cands: list[RunVideo]) -> RunVideo | None` — newest by `run_id` when every `run_id` matches `RUN_ID`, else by `mtime`.

- [ ] **Step 1: Write the failing tests** in `tests/test_walker.py`, building a fake Walker home under `tmp_path` with `monkeypatch.setenv("WALKER_HOME", ...)` and a source tree like `examples/cube/series` (`series.yaml` with `format: walker/0.2`, `series: {name: cube-gs, title: "Cube: getting started"}`, `episodes: [ep1, ep2]`):
  - `test_detect_kinds`: series folder → `"series"`; `ep1/` (with `walker.yaml`) → `"episode"`; `repo/.walker/` with `walker.yaml` → `"single"`; folder with only `a.mp4` → `"plain"`.
  - `test_repo_name_from_dot_walker_path`: `load_source(tmp/"myrepo"/".walker"/"series"/"cube")`.repo_name == `"myrepo"`; same for single `tmp/"myrepo"/".walker"`; outside a `.walker` folder → `None`.
  - `test_series_name_not_folder_name`: folder `series/cube/` with `series.name: cube-gs` → `video_root(...)` ends with `myrepo/series/cube-gs/ep1/video` and `expected_stem(src, "ep1") == "cube-gs-ep1"`.
  - `test_expected_stem_single`: `walked_tag: v1.2` → `"myrepo-v1.2"`; no tag → `"myrepo"`; `sanitize("a b/c") == "a-b-c"`.
  - `test_walker_home_order`: `WALKER_HOME` wins; without it, `home:` in `~/.walker/config.yaml` (use `monkeypatch.setenv("HOME"/"USERPROFILE")`); else `~/.walker`.
  - `test_find_runs_ignores_stray_and_explainer`: runs `20261027-100000/cube-gs-ep1.mp4`, `20261027-110000/explainer.mp4`, `notes/readme.txt` → one candidate, one explainer folder.
  - `test_choose_run_timestamp_ids`: `20261027-100000` and `20261028-090000` → the second, even if its mtime is older.
  - `test_choose_run_falls_back_to_mtime`: ids `a` and `b` → the newer mtime.
- [ ] **Step 2: Run** `uv run pytest tests/test_walker.py -q` — Expected: FAIL (`ModuleNotFoundError: metatube_helper.walker`).
- [ ] **Step 3: Implement `walker.py`** with the signatures above. Read YAML with `YAML(typ="safe")`, UTF-8.
- [ ] **Step 4: Run** `uv run pytest -q` — Expected: all pass.
- [ ] **Step 5: Commit** `feat(walker): read Walker source folders and choose a run`.

### Task 2: Manifest (`metatube.yaml`)

**Files:**
- Create: `skills/metatube/helper/src/metatube_helper/manifest.py`
- Test: `skills/metatube/helper/tests/test_manifest.py`

**Interfaces:**
- Produces:
  - `MANIFEST_NAME = "metatube.yaml"`; `SINGLE_KEY = "video"` (the episode key for a single Walker video).
  - `@dataclass EpisodeRecord: run_id: str | None = None; pin_run: str | None = None; video_id: str | None = None; blank_caption: bool = False`
  - `@dataclass PlaylistRecord: title: str; description: str; privacy: str; id: str | None = None; added: list[str] = field(default_factory=list)`
  - `@dataclass Manifest: repo: str | None = None; episodes: dict[str, EpisodeRecord] = ...; playlist: PlaylistRecord | None = None`
  - `load_manifest(folder: Path) -> Manifest` (missing file → empty `Manifest()`); `save_manifest(folder: Path, m: Manifest) -> Path` (UTF-8, atomic `.tmp` + `os.replace`, as `sidecars.write_sidecar`).
  - `@dataclass Conflict: episode: str; manifest_id: str; sidecar_id: str`
  - `sync_ids(m: Manifest, live: dict[str, tuple[str, str]]) -> tuple[Manifest, list[Conflict]]` — `live` maps episode → `(run_id, sidecar video_id)`. Empty manifest id → copy id and run_id. Equal → refresh run_id. Different → a `Conflict`, record unchanged.

- [ ] **Step 1: Write the failing tests:**
  - `test_round_trip_utf8`: playlist title `"Cube — café"` survives `save_manifest` → `load_manifest`; the file bytes decode as UTF-8.
  - `test_missing_manifest_is_empty`.
  - `test_sync_copies_sidecar_id`: empty record + `live={"ep1": ("20261027-100000", "AAAAAAAAAAA")}` → record has both, no conflicts.
  - `test_sync_conflict_leaves_record`: record `video_id="BBBBBBBBBBB"`, live id `AAAAAAAAAAA` → one `Conflict`, record still `BBBBBBBBBBB`.
  - `test_unknown_keys_ignored_on_load`.
- [ ] **Step 2: Run** `uv run pytest tests/test_manifest.py -q` — Expected: FAIL (module missing).
- [ ] **Step 3: Implement `manifest.py`.**
- [ ] **Step 4: Run** `uv run pytest -q` — Expected: all pass.
- [ ] **Step 5: Commit** `feat(manifest): metatube.yaml bookkeeping, sidecar ids win`.

### Task 3: Episode states and the `walker-status` / `walker-sync` subcommands

**Files:**
- Create: `skills/metatube/helper/src/metatube_helper/episodes.py`
- Modify: `skills/metatube/helper/src/metatube_helper/discover.py` (rename `_is_thin` → `is_thin`, keep behaviour)
- Modify: `skills/metatube/helper/src/metatube_helper/cli.py`
- Test: `skills/metatube/helper/tests/test_episodes.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: Task 1 (`WalkerSource`, `find_runs`, `choose_run`, `video_root`, `expected_stem`), Task 2.
- Produces:
  - `Status = Literal["ready", "live", "not_rendered", "explainer_only", "live_run_missing", "disagreement"]`
  - `@dataclass EpisodeState: key: str; position: int; status: Status; run: RunVideo | None; newer_run: str | None; video_id: str | None; notes: list[Path]; transcript: Path | None; thin_sources: list[Path]; message: str = ""` with property `has_source`.
  - `resolve(src: WalkerSource, m: Manifest) -> list[EpisodeState]`, rules in order:
    1. Candidates with a sidecar `video_id`: two different ids → `disagreement`; else the newest such run is the live `run`, status `live`, and `newer_run` = the `choose_run` id if it is a different, later run.
    2. Manifest has a `video_id` but no run carries it → `live_run_missing`.
    3. Manifest `video_id` ≠ the live run's sidecar id → `disagreement`.
    4. Not live: `pin_run` if set and present, else `choose_run(cands)` → `ready`; no candidate but explainer folders → `explainer_only` (message tells the owner to re-render or give the video id); nothing → `not_rendered`.
  - Notes: episode `story.md`, `screenplay.md`, plus the series `story.md` (series only); single: `story.md`, `screenplay.md`. `transcript` = the run's `srt`. `thin_sources` via `discover.is_thin`.
  - `walker_entries(states: list[EpisodeState]) -> list[VideoEntry]` — `discover(state.run.folder)` entry for every state with a `run`.
  - CLI `walker-status SOURCE [--repo NAME]`: `detect` → `episode` → `_error("this is an episode; point me at the series folder: <parent>", 2)`; `plain` → `_error(..., 2)`. `--repo` saves `Manifest.repo`. `repo_name` = argument, else path rule, else `Manifest.repo`; still `None` → `_error("repo name unknown; pass --repo <name Walker uses under ~/.walker>", 1)`. Prints `{"kind", "title", "repo", "video_root_base", "episodes": [EpisodeState...], "playlist": ...}`.
  - CLI `walker-sync SOURCE`: `sync_ids` from the `live` states, saves; exit 1 with `conflicts` if any.

- [ ] **Step 1: Write the failing tests** (fake home + source as Task 1):
  - `test_not_rendered_episode`: `episodes: [ep1, ep2]`, only ep1 rendered → ep2 `not_rendered`, no exception; ep2 folder missing entirely → same.
  - `test_ready_picks_newest_and_pin`: two runs → newest; `pin_run` set to the older → older.
  - `test_live_run_sticks`: older run sidecar has `video_id`, newer run has none → `live`, `run` = older, `newer_run` = newer id, `transcript` = older run's `.srt`.
  - `test_two_live_runs_same_id`: both sidecars hold the same id → `live`, newest of them.
  - `test_two_live_runs_different_ids`: → `disagreement`.
  - `test_manifest_disagrees_with_sidecar`: → `disagreement`, manifest untouched after `walker-sync` exits 1.
  - `test_live_run_missing`: manifest id, no runs → `live_run_missing`.
  - `test_explainer_only`.
  - `test_cli_walker_status_episode_folder_exit_2`, `test_cli_walker_status_unknown_repo_then_repo_flag` (second call without `--repo` reads it from the manifest), `test_cli_walker_sync_copies_ids`.
- [ ] **Step 2: Run** `uv run pytest tests/test_episodes.py tests/test_cli.py -q` — Expected: new tests FAIL.
- [ ] **Step 3: Implement** `episodes.py`, the rename in `discover.py`, and both subcommands in `cli.py` (`_parser`).
- [ ] **Step 4: Run** `uv run pytest -q` — Expected: all pass.
- [ ] **Step 5: Commit** `feat(walker): episode states, walker-status and walker-sync`.

### Task 4: v1 subcommands accept a Walker source

**Files:**
- Modify: `skills/metatube/helper/src/metatube_helper/cli.py` (`cmd_match`, `cmd_set_video_id`, `cmd_quota`)
- Modify: `skills/metatube/helper/src/metatube_helper/ytstudio.py` (`estimate_quota`)
- Test: `tests/test_cli.py`, `tests/test_ytstudio.py`

**Interfaces:**
- Consumes: Task 3 (`resolve`, `walker_entries`), Task 1 (`detect`, `load_source`).
- Produces:
  - `cli._walker_states(folder: Path) -> tuple[WalkerSource, Manifest, list[EpisodeState]] | None` (None for plain folders).
  - `match FOLDER`: Walker source → `match_videos(walker_entries(states), channel)`; plain → unchanged.
  - `set-video-id SIDECAR REF [--source SOURCE]`: with `--source`, the duplicate check covers every episode's `run.video_id` and manifest id, not only `sidecar.parent`.
  - `estimate_quota(uploads=0, updates=0, playlist_creates=0, playlist_adds=0, caption_lists=0, caption_inserts=0) -> int` with the Global Constraints units.
  - `quota FOLDER --mode update|upload` on a Walker series: counts states `ready`/`live` with a sidecar; adds one playlist create (if `Manifest.playlist.id` is unset) and one add per such episode not in `playlist.added`. Captions are added in Task 7.
- [ ] **Step 1: Write the failing tests:** `test_match_walker_series` (two rendered episodes with sidecars, fake `list_channel_videos` returning titles `"cube gs ep1"`, `"cube-gs-ep2"` → both `matched`); `test_set_video_id_source_refuses_id_held_by_other_episode`; `test_quota_walker_series_counts_playlist` (2 episodes, no playlist → `2*50 + 50 + 2*50 = 250`); `test_estimate_quota_new_kinds`.
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q` — Expected: all pass.
- [ ] **Step 5: Commit** `feat(walker): match, set-video-id and quota on Walker sources`.

### Task 5: Playlist

**Files:**
- Create: `skills/metatube/helper/src/metatube_helper/playlists.py`
- Modify: `skills/metatube/helper/src/metatube_helper/ytstudio.py`, `cli.py`
- Modify: `skills/metatube/references/cli-contract.md` (new "Playlists" section)
- Test: `tests/test_playlists.py`, `tests/test_ytstudio.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: Tasks 2–3.
- Produces in `ytstudio.py` (all via `run_ytstudio`, `RuntimeError` on non-zero exit):
  - `@dataclass PlaylistInfo: id: str; title: str; item_count: int; privacy: str`; `@dataclass PlaylistItem: video_id: str; title: str; position: int`
  - `list_playlists(profile) -> list[PlaylistInfo]` — `playlists list -n 50 -o json` → `{"playlists": [...]}`.
  - `playlist_items(playlist_id, profile) -> list[PlaylistItem]` — `playlists items <id> -n 500 -o json` → `{"items": [...]}`.
  - `create_playlist_argv(title, description, privacy, language, execute) -> list[str]`; `parse_created_id(stdout: str) -> str` — regex `Created: .* \(([A-Za-z0-9_-]+)\)\s*$` (multiline); `ValueError` if absent.
  - `add_argv(playlist_id, video_id, position: int, execute) -> list[str]` — `["playlists", "add", playlist_id, "--video", video_id, "--position", str(position)] (+ "--execute")`. Pass `"--"` before the playlist id if it starts with `-`, as `update_argv` does.
- Produces in `playlists.py` (pure):
  - `lint_playlist(title: str, description: str, privacy: str) -> list[str]` errors: empty title, title > 150 chars, description > 5000 chars, `<` or `>` in either, privacy not in `public|private|unlisted`. `create_playlist_argv` passes `--language` = config `defaults.default_language`.
  - `insert_position(order: list[str], episode_video: str, items: list[PlaylistItem]) -> int` — `order` = series video ids in episode order; position = (index of the last item whose video is an earlier episode) + 1, else 0.
  - `plan_adds(states, m, items) -> list[tuple[str, str, int]]` — `(episode, video_id, position)` for live episodes not in `items`, in series order, positions recomputed as if earlier adds were done.
  - `flag_items(items, known_ids: set[str], series_title: str) -> list[PlaylistItem]` — items whose id isn't known and whose title doesn't contain `series_title` (casefolded).
- CLI:
  - `playlist-draft SOURCE --from DRAFT` — DRAFT is YAML `{title, description, privacy}`; `lint_playlist`; refuses on a single Walker source; writes `Manifest.playlist` keeping an existing `id`/`added`.
  - `playlist SOURCE [--execute]`:
    - No `playlist` in manifest → `_error("no playlist draft; run generate")`.
    - No `id` → `list_playlists`; same title (casefolded, stripped) → exit 1 with `{"collision": [{id, title, items, flagged}]}`, nothing created. Otherwise dry run shows the create argv; `--execute` runs it, `parse_created_id`, saves the id **before** adding.
    - Then `plan_adds`; dry run lists them; `--execute` runs each `add_argv`, then re-reads `playlist_items` and records in `added` only ids actually present; any not present → `not_added` in the output, exit 1.
  - `playlist-adopt SOURCE PLAYLIST_ID` — prints the items and `flagged`; with `--confirm`, saves the id to the manifest (the skill only passes `--confirm` after the owner's yes with the flagged list in view).
- `cli-contract.md`: document `list -o json`, `items -o json`, `create` output `Created: <title> (<id>)` (no JSON, default privacy private), `add` (50 units per video, prints `Done: N added, M failed` and exits 0 even when some failed), verified against installed 0.4.2.

- [ ] **Step 1: Verify the contract** against the installed ytstudio 0.4.2: `ytstudio playlists list --help`, `items --help`, `create --help`, `add --help`. If any flag or output differs from the above, update this task's interfaces before writing tests.
- [ ] **Step 2: Write the failing tests:** `test_parse_created_id` (`"✓ Created: Cube — café (PLabc_123-x)\n"` → `PLabc_123-x`; garbage → `ValueError`); `test_insert_position` (order `[a,b,c]`, items `[a, x, c]`, inserting `b` → 2; items `[]` → 0; items `[c]` inserting `a` → 0); `test_plan_adds_skips_present_and_orders`; `test_flag_items`; `test_lint_playlist`; `test_playlist_collision_stops` (fake `list_playlists` with same title → exit 1, no create call recorded); `test_playlist_execute_creates_then_adds` (fake `run_ytstudio` records argv; manifest id saved before the first add); `test_playlist_add_reported_failed` (add exits 0 but `playlist_items` lacks the video → `not_added`, exit 1, not in `added`); `test_playlist_adopt_requires_confirm`; `test_playlist_draft_refuses_single`.
- [ ] **Step 3: Run** — Expected: FAIL.
- [ ] **Step 4: Implement** `playlists.py`, the ytstudio wrappers, the CLI subcommands; update `cli-contract.md`.
- [ ] **Step 5: Run** `uv run pytest -q` — Expected: all pass.
- [ ] **Step 6: Commit** `feat(playlists): one playlist per Walker series, in episode order`.

### Task 6: Captions spike (blocking for Task 7)

**Files:**
- Create: `skills/metatube/helper/src/metatube_helper/yt_captions.py` (standalone: imports only stdlib, `googleapiclient.http.MediaInMemoryUpload` and `ytstudio.services`; never `metatube_helper`)
- Modify: `skills/metatube/helper/src/metatube_helper/ytstudio.py`
- Test: `tests/test_ytstudio.py`, `tests/test_yt_captions.py`

**Interfaces:**
- Produces:
  - `yt_captions.py` CLI, run as `<ytstudio python> yt_captions.py list VIDEO_ID` → `{"tracks": [{"id", "language", "name", "kind"}]}`; `... insert VIDEO_ID --language en` → `{"inserted": "<track id>"}`. Errors → `{"error": "..."}` and exit 1. It calls `get_data_service()` and `captions().list(part="snippet", videoId=...)` / `captions().insert(part="snippet", body={"snippet": {"videoId", "language", "name": "", "isDraft": False}}, media_body=MediaInMemoryUpload(ONE_CUE_SRT.encode(), mimetype="application/octet-stream"))`. It never prints credentials.
  - `yt_captions.ONE_CUE_SRT = "1\n00:00:00,000 --> 00:00:01,000\n.\n"`
  - `ytstudio.ytstudio_python() -> Path | None` — from `uv tool dir` (subprocess) + `ytstudio-cli/Scripts/python.exe` (Windows) or `ytstudio-cli/bin/python`; `None` if missing.
  - `ytstudio.run_captions(args: list[str], profile: str | None) -> RunResult` — runs `[ytstudio_python(), <path of yt_captions.py>, *args]` with the same env as `run_ytstudio`; returncode 127 when the interpreter is missing.
- [ ] **Step 1: Write the failing tests:** `test_one_cue_srt_exact`; `test_ytstudio_python_paths` (fake `uv tool dir` output, both layouts); `test_run_captions_env_and_argv` (fake subprocess: `YTSTUDIO_PROFILE`, `PYTHONUTF8` set; argv ends with the script and args).
- [ ] **Step 2: Run** — Expected: FAIL. **Step 3: Implement.** **Step 4: Run** `uv run pytest -q` — Expected: pass.
- [ ] **Step 5: Commit** `feat(captions): spike script run with ytstudio's own Python`.
- [ ] **Step 6: Live check, with the owner.** Ask the owner for one test video id they're happy to use (not the series). Show both commands first, and run them only after the owner says yes:
  1. `list <id>` (50 units)
  2. `insert <id> --language en` (400 units)

  Pass when both of these hold:
  - (a) the insert succeeds without a new consent screen;
  - (b) the owner opens the watch page with CC on and sees no automatic captions, only the burned-in text.

  Record the result in the spec's §7, then commit `docs: captions spike result`.
- [ ] **Step 7: Gate.** If (a) or (b) failed, **stop here**: report to the owner and skip Task 7. Task 8 still runs, without the captions parts.

### Task 7: Blank captions (only after the Task 6 spike passed)

**Files:**
- Create: `skills/metatube/helper/src/metatube_helper/captions.py`
- Modify: `config.py`, `cli.py`, `ytstudio.py` (`estimate_quota` already has the kinds)
- Test: `tests/test_captions.py`, `tests/test_config.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: Task 6 (`run_captions`), Task 3 (states), Task 2 (`EpisodeRecord.blank_caption`).
- Produces:
  - `Config.blank_captions: str = "walker"`; `set_value` accepts only `walker|always|never` for it (`ValueError` otherwise). `config show` includes it.
  - `captions.enabled(setting: str, walker_source: bool) -> bool` — `always` → True, `never` → False, `walker` → `walker_source`.
  - `captions.plan(targets: list[tuple[str, str, str]], tracks: dict[str, list[dict]]) -> tuple[list[tuple[str, str, str]], list[dict]]` — targets are `(key, video_id, language)`; a target whose tracks include any `kind != "asr"` is skipped (`{"key", "video_id", "reason": "has a non-automatic track"}`).
  - CLI `captions TARGET [--execute]`: TARGET is a Walker source (live states; language from each sidecar's `default_language` or config default) or a plain folder (live sidecars). Setting off → `{"enabled": false}`, exit 0. For each video, `run_captions(["list", id])` (dry run included: reads are part of the plan), then `plan`. `--execute` → `insert` for each, and on success sets `EpisodeRecord.blank_caption = True` (Walker sources). Output: `to_insert`, `skipped`, `results`, `estimated_units`.
  - `quota`: adds `caption_lists`/`caption_inserts` for live videos when the setting is on.
- [ ] **Step 1: Write the failing tests:** `test_enabled_matrix`; `test_config_blank_captions_validates` (`"walker"`, `"always"`, `"never"` ok; `"yes"` → `ValueError`); `test_plan_skips_manual_track` (tracks `[{"kind": "standard"}]` → skipped; `[{"kind": "asr"}]` → inserted); `test_captions_cli_dry_run_no_insert` (fake `run_captions` records calls: only `list`); `test_captions_cli_execute_marks_manifest`; `test_captions_cli_disabled_for_plain_by_default`.
- [ ] **Step 2: Run** — Expected: FAIL. **Step 3: Implement.** **Step 4: Run** `uv run pytest -q` — Expected: pass.
- [ ] **Step 5: Commit** `feat(captions): one-cue track to hide automatic captions`.

### Task 8: Skill workflow, docs and the Walker example

**Files:**
- Modify: `skills/metatube/SKILL.md`, `skills/metatube/references/sidecar-schema.md` (note `metatube.yaml` is separate), `skills/metatube/references/seo-guide.md` (series: no prev/next links; the playlist links episodes), `README.md` (roadmap: tick playlists; describe Walker sources)
- Create: `examples/walker-series/` — source side (`series.yaml`, `story.md`, `ep1-intro/story.md`, `ep1-intro/screenplay.md`, `ep2-usage/...`, `metatube.yaml` with a playlist draft) and `examples/walker-series/_home/myrepo/series/demo/<ep>/video/20261027-100000/demo-<ep>.{srt,yaml}` (no `.mp4`; tests create empty ones)
- Modify: `tests/test_examples.py`

**Interfaces:**
- Consumes: all previous tasks' CLI subcommands.
- SKILL.md changes:
  - `allowed-tools`: add the read-only `walker-status *` and `playlist-adopt *` (without `--confirm`)
  - helper subcommand list: add `walker-status`, `walker-sync`, `playlist-draft`, `playlist`, `playlist-adopt` and, if Task 7 shipped, `captions`
  - **generate**:
    - start with `walker-status`, and on `repo name unknown` ask the owner once and pass `--repo`
    - show the episode table: key, status, chosen run and video path, newer render, `video_id`
    - `explainer_only` is a hard stop until the owner re-renders or gives the id
    - draft only `ready` episodes and `live` ones the owner asks to redraft
    - write sidecars into the run folder with `write-sidecar`
    - draft the playlist (series only) in the same review gate, then write it with `playlist-draft`
  - **publish**:
    - `walker-status`, then `match` and `set-video-id --source`, then `walker-sync`
    - then `update` per live sidecar, then `playlist`, then `captions`
    - each step dry run first and asks for a yes
    - a `collision` goes to `playlist-adopt`, and its `--confirm` is passed only after the owner's yes
    - the playlist draft's privacy defaults to config `defaults.privacy`
    - upload mode: `upload <run folder>` for each `ready` episode with a sidecar, never for `live` ones; then
      `walker-sync`, `playlist` and `captions`, as in update mode
  - Guardrails:
    - the manifest never overwrites a sidecar's `video_id`
    - a video with a `video_id` is never uploaded again
    - the one stated exception to "never call the YouTube API yourself": `captions` via ytstudio's own Python
  - setup step 7: show `blank_captions` and offer to change it
- [ ] **Step 1: Write the failing tests:**
  - in `test_examples.py`, keep `FOLDERS = ["single-video", "series"]` for the flat examples
  - make `all_sidecars()` take the flat examples only (`EXAMPLES.glob("*/*.yaml")` minus `walker-series`)
  - `test_walker_example_status`: copy `examples/walker-series` to `tmp_path`, set `WALKER_HOME` to its `_home`, add the empty `.mp4`s, run `walker-status <copy> --repo myrepo` → both episodes `ready`, transcripts found, and `has_source` true
  - `test_walker_example_sidecars_lint_clean`
  - `test_walker_example_playlist_draft_lints`
- [ ] **Step 2: Run** — Expected: FAIL (example missing).
- [ ] **Step 3: Write the example and the doc changes** above. Re-read `SKILL.md` top to bottom for consistency with v1 wording and guardrails.
- [ ] **Step 4: Run** `uv run pytest -q` — Expected: all pass.
- [ ] **Step 5: Commit** `docs: Walker sources, playlists and captions in the skill`.
