# Screenplay: ep2-usage

1. Add `max_retries=3` to a job that raises on its first two runs; show the attempts column climb.
2. Enqueue a job with `run_at` five minutes ahead and show the worker leave it alone until then.
3. Start three workers in three terminals, enqueue twenty jobs, and count which worker ran each one.
