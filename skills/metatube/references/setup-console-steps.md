# Google Cloud Console steps (manual, about 5 minutes)

Google has no API for these steps, so the user clicks through them once. Replace `<PROJECT_ID>`.

## 1. OAuth consent screen

Open https://console.cloud.google.com/apis/credentials/consent?project=<PROJECT_ID>

1. User type: **External** → Create.
2. App name (for example "MetaTube"), user support email, developer contact email → Save and
   continue.
3. Scopes: skip (ytstudio requests them at login) → Save and continue.
4. Test users: **add your own Google account** (the one that owns the channel) → Save.
5. Leave the publishing status as **Testing**.

In Testing mode Google expires the login after 7 days. MetaTube detects this and asks you to run
`ytstudio login` again. Newer Console versions call this area "Google Auth Platform", with
"Branding", "Audience" and "Clients" pages; the choices are the same.

## 2. OAuth client

Open https://console.cloud.google.com/apis/credentials?project=<PROJECT_ID>

1. Create credentials → **OAuth client ID**.
2. Application type: **Desktop app**. Name: "MetaTube" → Create.
3. **Download JSON**, note where you saved it, and give MetaTube the path.

Keep this file private and never commit it (`client_secret*.json` is in `.gitignore`).
