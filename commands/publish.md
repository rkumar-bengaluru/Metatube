---
description: Apply approved sidecars to YouTube - update existing Studio uploads or upload new videos
argument-hint: "<folder> [--mode update|upload] [--max N]"
---

Use the metatube skill to run the **publish** workflow. Arguments: $ARGUMENTS

- `--mode update`: apply title, description and tags to videos already uploaded in YouTube Studio.
- `--mode upload`: upload the videos with ytstudio-cli (only useful once the API audit has passed).
- Without `--mode`, use the mode from `metatube-helper config show`.
- `--max N` caps the number of uploads in this run.
