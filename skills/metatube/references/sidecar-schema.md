# Sidecar schema

One YAML file per video with the same basename (`episode-01.mp4` → `episode-01.yaml`), UTF-8.
This is ytstudio-cli's schema; **any other key is rejected**.

| Key | Required | MetaTube default | Notes |
| --- | --- | --- | --- |
| `title` | yes | — | 1–100 chars; aim for 70 or fewer |
| `description` | no | — | multi-line; use a `\|` block |
| `privacy` | no | `public` | `public`, `unlisted`, `private`; forced to `private` by `publish_at` |
| `publish_at` | no | — | ISO datetime with timezone, in the future |
| `tags` | no | — | list of 8–15; 500 chars total at most; no commas inside a tag |
| `category_id` | yes | `"28"` | string. 28 = Science & Technology, 27 = Education |
| `default_language` | no | `en` | |
| `default_audio_language` | no | `en` | |
| `made_for_kids` | no | `false` | `true` only for content aimed at children under 13 (COPPA) |
| `video_id` | — | — | written by ytstudio after upload, or by `set-video-id` after matching. Never edit or remove |
| `uploaded_at` | — | — | written by ytstudio |

Defaults come from `metatube-helper config show` → `defaults`.

```yaml
title: "Repo Tour Ep. 1: Installing and Running acme-cli"
description: |
  Install acme-cli from GitHub and run your first command in under five minutes.

  We clone the repo, install dependencies with uv, and run the sample pipeline.

  00:00 Intro
  00:45 Cloning the repo
  02:10 First run

  Repo: https://github.com/example/acme-cli

  #GitHub #Python
tags: [acme-cli, acme cli tutorial, github repo tutorial, python cli, uv install, cli pipeline, acme-cli install, python tooling]
category_id: "28"
privacy: public
made_for_kids: false
default_language: en
default_audio_language: en
```

In update mode only `title`, `description` and `tags` are applied; the other fields tell the
user what to set in Studio.

## Not a sidecar: `metatube.yaml`

A Walker source folder also holds `metatube.yaml`, MetaTube's bookkeeping for the series or single Walker
video: the repo name under Walker's home, per-episode `run_id`, `pin_run` and `video_id`, and for a series
the `playlist` (title, description, privacy, id, and the video ids added). It is written by the helper
(`walker-status --repo`, `walker-sync`, `playlist-draft`, `playlist`, `playlist-adopt`); the owner edits it by
hand only to set `pin_run`, or to remove a wrong `video_id` after `walker-sync` reports a conflict. None of its keys go into a sidecar. The sidecar is the source of truth for a video's
`video_id`; `metatube.yaml` only copies it.
