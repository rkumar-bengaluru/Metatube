# Example: Walker series

A two-episode Walker series, "tinyqueue Tour", about the fictional `tinyqueue` repo.

- `series.yaml`: the series (name `demo`, title, episode order, project and repo link)
- `story.md`, `epN-*/story.md`, `epN-*/screenplay.md`: the notes MetaTube drafts from
- `metatube.yaml`: MetaTube's bookkeeping, here with the playlist draft (title, description, privacy)
- `_home/myrepo/series/demo/<episode>/video/<run>/`: a fake Walker home holding each episode's rendered run:
  the transcript (`demo-<episode>.srt`) and the sidecar MetaTube would write after review
  (`demo-<episode>.yaml`). The `.mp4` files aren't committed.

Try it: set `WALKER_HOME` to this folder's `_home`, then `/metatube:generate examples/walker-series`.
