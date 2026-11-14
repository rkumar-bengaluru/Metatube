"""One YouTube playlist per Walker series, holding its live episodes in series order. Pure logic, no I/O."""

from metatube_helper.episodes import EpisodeState
from metatube_helper.manifest import Manifest
from metatube_helper.ytstudio import PlaylistItem

PRIVACY = ("public", "private", "unlisted")
TITLE_MAX = 150
DESCRIPTION_MAX = 5000
# Episodes that are on YouTube with an agreed video id. `disagreement` is left out: its id is in doubt.
LIVE = ("live", "live_run_missing")


def lint_playlist(title: str, description: str, privacy: str) -> list[str]:
    errors = []
    if not title.strip():
        errors.append("playlist title is empty")
    if len(title) > TITLE_MAX:
        errors.append(f"playlist title is {len(title)} characters; YouTube allows {TITLE_MAX}")
    if len(description) > DESCRIPTION_MAX:
        errors.append(f"playlist description is {len(description)} characters; YouTube allows {DESCRIPTION_MAX}")
    for name, text in (("title", title), ("description", description)):
        if "<" in text or ">" in text:
            errors.append(f"playlist {name} contains < or >, which YouTube rejects")
    if privacy not in PRIVACY:
        errors.append(f"playlist privacy must be one of {', '.join(PRIVACY)}, not {privacy!r}")
    return errors


def insert_position(order: list[str], episode_video: str, items: list[PlaylistItem]) -> int:
    """Where `episode_video` goes in `items` (playlist order) so the series' episodes stay in `order`.

    Right before the first later episode already in the playlist; with none, right after the last
    earlier episode; with neither, at the top.
    """
    i = order.index(episode_video)
    earlier, later = set(order[:i]), set(order[i + 1:])
    for pos, item in enumerate(items):
        if item.video_id in later:
            return pos
    last = max((pos for pos, item in enumerate(items) if item.video_id in earlier), default=-1)
    return last + 1


def plan_adds(states: list[EpisodeState], m: Manifest, items: list[PlaylistItem]) -> list[tuple[str, str, int]]:
    """(episode, video_id, position) for live episodes not yet in the playlist, in series order.

    Each position counts the adds planned before it. Videos MetaTube already added (`added`) are not
    added again even if they are gone from the playlist: the owner removed them in Studio.
    """
    live = [s for s in states if s.status in LIVE and s.video_id]
    order = [s.video_id for s in live]
    done = {item.video_id for item in items} | set(m.playlist.added if m.playlist else [])
    current = list(items)
    plan = []
    for s in live:
        if s.video_id in done:
            continue
        pos = insert_position(order, s.video_id, current)
        current.insert(pos, PlaylistItem(s.video_id, "", pos))
        done.add(s.video_id)
        plan.append((s.key, s.video_id, pos))
    return plan


def flag_items(items: list[PlaylistItem], known_ids: set[str], series_title: str) -> list[PlaylistItem]:
    """Items to show the owner: not one of the series' video ids, or not carrying the series title."""
    wanted = series_title.casefold()
    return [i for i in items if i.video_id not in known_ids or wanted not in i.title.casefold()]
