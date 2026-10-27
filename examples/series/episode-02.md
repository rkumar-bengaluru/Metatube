# tinyqueue Deep Dive, episode 2: scheduling and retries

Repo: https://github.com/example/tinyqueue

- Delayed jobs: `job.delay_until(datetime)` sets `run_at`.
- Cron-style schedules with `@tinyqueue.every("5m")`.
- Retry policy: `retries=3`, exponential backoff, jitter.
- Dead jobs: inspecting and re-queuing with `tinyqueue jobs --failed --requeue`.
