# Screenplay: ep1-intro

1. `pip install tinyqueue` in a fresh virtual environment.
2. Write `tasks.py` with a `send_welcome_email(user_id)` function and a `Queue("jobs.db")`.
3. Enqueue one call from the Python shell; open `jobs.db` with `sqlite3` and show the pending row.
4. Start `tinyqueue worker tasks` in a second terminal and watch the job run and the row turn `done`.
