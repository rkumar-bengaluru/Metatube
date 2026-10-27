# tinyqueue Deep Dive, episode 1: architecture

Repo: https://github.com/example/tinyqueue

- How jobs are stored: one SQLite table, `jobs`, with status, payload, attempts, run_at.
- How workers claim jobs safely: `UPDATE ... RETURNING` inside a transaction.
- Why SQLite WAL mode matters for concurrent workers.
- Walk through `tinyqueue/worker.py` main loop.
