# Applying for the YouTube API compliance audit

Why: videos uploaded through the API from a Cloud project that hasn't passed the YouTube API
Services audit (projects created after July 2020) are locked private. Until it passes, upload in
YouTube Studio and use `/metatube:publish --mode update`.

1. Open the **YouTube API Services – Audit and Quota Extension Form** at
   https://support.google.com/youtube/contact/yt_api_form, signed in as the account that owns the
   Cloud project.
2. Have ready:
   - legal name or organization name, website, address, contact email
   - the Cloud **project number** (Console → project dashboard)
   - the OAuth client in use
   - a plain description of how the tool uses the API
   - whether you commercialize YouTube data (MetaTube: no)
   - screenshots or a short screencast of the tool working (for example a dry run and an update)
3. Describe it accurately: "A single-owner internal tool that uploads my own training videos to my
   own channel and edits their titles, descriptions and tags. No other users. It doesn't store,
   share or resell YouTube data."
4. Tick the quota-extension option only if you need more than about 6 uploads a day.
5. Submit. Google replies by email, usually within days to a few weeks, and may ask follow-up
   questions.
6. When it passes, run `metatube-helper config set audit_passed true` (or re-run
   `/metatube:setup`). Upload mode then becomes the default.

Google's process guide: https://developers.google.com/youtube/data/guides/quota_and_compliance_audits
