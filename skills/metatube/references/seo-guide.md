# SEO guide for MetaTube drafts

Goal: every query the video genuinely answers should find it. Audience: developers.

## Before drafting

Write a one-sentence summary of what the video teaches, then list the queries a developer would
type: repo name, tool and library names, the task ("install X on Windows"), error messages shown
on screen, concepts. Only use what the sources show.

## Title

- 70 characters or fewer (hard limit 100). Put the main query phrase in the first ~40 characters.
- Say what the viewer gets: "Install acme-cli and Run Your First Pipeline".
- Series: `Series Name Ep. N: Topic`, consistent across episodes.
- No clickbait, ALL CAPS, emoji spam, or promises the video doesn't keep.

## Description

- First ~150 characters (shown in search): the core keyword and what the viewer will be able to do.
- Then 2–4 short paragraphs: what's covered, prerequisites, who it's for.
- Chapters **only from a transcript** (`.srt`/`.vtt`): the first at `00:00`, at least 3 chapters,
  each at least 10 seconds long. No transcript means no chapters. Never guess timestamps from a
  script.
- Links found in the notes: the repo URL, docs. In a series, link the previous/next episodes if
  known.
- 2–3 hashtags at the end.

## Tags

- 8–15 tags, 500 characters total at most, no commas inside a tag.
- Mix broad (`github tutorial`, `python cli`) and specific (`acme-cli install`, `acme-cli config`).
- Include common spellings of the repo or tool name (`acme cli`, `acme-cli`).

## Anti-patterns (never)

- Keyword stuffing: repeated keywords, or tag lists pasted into the description.
- Tags or titles naming tools, brands or competitors the video doesn't cover.
- Misleading titles.
- Chapters invented without a transcript.
- Claims the sources don't support.
