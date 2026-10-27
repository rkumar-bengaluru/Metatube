# tinyqueue in 10 minutes: script

Repo: https://github.com/example/tinyqueue

## Intro
tinyqueue is a small background job queue for Python apps backed by SQLite. No Redis, no broker.
Today: install it, define a job, run a worker, and retry a failing job.

## Install
- `git clone https://github.com/example/tinyqueue`
- `uv pip install -e .`
- Show `tinyqueue --version`.

## Define a job
- `@tinyqueue.job` decorator on `send_welcome_email(user_id)`.
- Enqueue with `send_welcome_email.delay(42)`.

## Run a worker
- `tinyqueue worker --db jobs.sqlite`
- Show the job being picked up in the logs.

## Retries
- Raise an exception in the job; show `retries=3` with backoff.
- Show the failed job in `tinyqueue jobs --failed`.

## Wrap-up
Café-sized deployments don't need a broker. Next steps: scheduling and the web dashboard.
