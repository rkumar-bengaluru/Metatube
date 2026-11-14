# Episode 1: install tinyqueue and run a first job

We install tinyqueue from PyPI, create a queue backed by a SQLite file, enqueue a function call from one
terminal and watch a worker in a second terminal pick it up and run it. Along the way we look at the jobs
table so viewers see where the job lives while it waits.
