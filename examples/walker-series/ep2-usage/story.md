# Episode 2: retries, schedules and several workers

We make a job fail on purpose and watch tinyqueue retry it with backoff, schedule a job to run in five
minutes with `run_at`, and start three workers against the same SQLite file to show that each job is claimed
by exactly one of them.
