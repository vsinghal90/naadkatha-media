# Naad Katha Studio

A small web app where invited teammates see the Naad Katha post plan, watch each
post's video, read its hook, script and caption, leave notes, and (Owner or
Manager only) approve the final cut. Works on phone and desktop and can be added
to the home screen.

Step 1 of the plan in the design doc. Chat editing and in-app renders come next.

## How it fits together

- **App + API**: one Cloudflare Worker (`src/worker.js`) serving `public/`.
- **Database**: Cloudflare D1 (`schema.sql`): channels, members, posts, approvals, notes, history.
- **Videos and covers**: Cloudflare R2, private. Played only through the app, with sign-in.
- **Sign-in**: Cloudflare Access in front of the whole app (Google or a one-time email code).
  The app then checks the email against the Team list, so only invited people get in.
- **Sync** (`sync/sync.py`): run by the Claude project every 15 minutes. Reads
  `/mnt/project-files/naad-katha-posts/<slug>_<DDMMYY>/`, uploads changed videos,
  sends titles, hooks, captions and scripts, and writes approvals into `upload-text.md`.

## Roles

| Role | See plan and posts | Notes | Approve | Team |
| --- | --- | --- | --- | --- |
| Owner | yes | yes | yes | yes |
| Manager | yes | yes | yes | no |
| Editor | yes | yes | no | no |
| Viewer | yes | no | no | no |

## What an approval writes

The first line of `upload-text.md` becomes one of:

- `FINAL CUT. Owner approved 13 Nov 2026, 3:25 pm IST in Studio (Owner name).`
- `FINAL CUT. Approved by Asha (manager) 13 Nov 2026, 3:25 pm IST in Studio.`
- `NOT APPROVED. Approval withdrawn by Asha 13 Nov 2026, 4:02 pm IST in Studio.`

The old first line moves to line 2 as `Earlier status: ...`, and a backup copy goes
to `.studio-backups/`. The sync refuses to write an approval if the video file
changed after someone pressed Approve.

The auto-posting task must accept any first line starting with `FINAL CUT.`
(today it looks for `FINAL CUT. Owner approved`), so Manager approvals post too.

## One-time setup (about 15 minutes)

1. **Cloudflare account** (free): sign up at dash.cloudflare.com. Turning on R2
   asks for a card; nothing is charged inside the free limits (10 GB).
2. **API token**: My Profile → API Tokens → Create token → "Edit Cloudflare Workers"
   template, and add D1 Edit and R2 Edit. Copy the token and the Account ID.
3. **GitHub secrets** on this repo: `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`.
4. **Create storage** (once, from any machine with Node, or ask Claude to do it):
   ```
   cd studio && npm ci
   npx wrangler d1 create naadkatha-studio     # paste the id into wrangler.jsonc
   npx wrangler r2 bucket create naadkatha-studio-media
   npx wrangler secret put OWNER_EMAIL          # your Google email
   npx wrangler secret put SYNC_TOKEN           # long random string
   ```
5. **Sign-in**: Zero Trust → Access → Applications → Add → Self-hosted, domain =
   the Worker's address (`naadkatha-studio.<you>.workers.dev`). Policy "Allow",
   include "Everyone" (the app's Team list does the real gatekeeping). Login methods:
   One-time PIN works at once; for the Google button, add Google under Settings →
   Authentication (needs a free OAuth client in a Google Cloud project kept
   separate from the YouTube one). Copy the Application Audience (AUD) tag and
   the team domain into `wrangler.jsonc`.
   Add a **Service Auth** policy with a service token for the sync job.
6. Push to `main`: the GitHub Action deploys.
7. **Sync job**: in the Claude project, save `STUDIO_URL`, `STUDIO_SYNC_TOKEN`,
   `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET` as secrets, allow the Studio
   host in the environment's network list, and schedule
   `python3 studio/sync/sync.py` every 15 minutes.

## Run it locally

```
cd studio && npm ci
npm run db:local
npx wrangler dev            # uses .dev.vars (ENVIRONMENT=dev, fake sign-in)
STUDIO_URL=http://localhost:8787 STUDIO_SYNC_TOKEN=dev-sync-token \
  python3 sync/sync.py --root /path/to/a/copy/of/naad-katha-posts
```

`.dev.vars` (not committed):
```
ENVIRONMENT=dev
DEV_USER_EMAIL=owner@example.com
OWNER_EMAIL=owner@example.com
SYNC_TOKEN=dev-sync-token
```
In dev, send `x-dev-user: someone@example.com` to act as another member.
