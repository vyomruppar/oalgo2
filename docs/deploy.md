# Putting it on the web for free

Everything runs on two free services, with no credit card:

| Part | Runs on | What it does |
|---|---|---|
| Research engine | **GitHub Actions** (free for public repositories) | Every weekday after the US close, and whenever you change something on the dashboard: applies your changes, scans about 300 stocks, scores headlines with FinBERT, then publishes the results |
| Dashboard | **Vercel** (free Hobby plan) | Shows every page behind your password, and passes your changes to GitHub |

Your repository is public, so nothing private is stored in it in readable form. The engine's database (your holdings included) is encrypted with a secret only you hold, and so is every change you make on the dashboard while it waits to be applied. Run logs show counts only.

## What is different from running it on your computer

- **Changes are not instant.** Adding a holding, saving settings or fetching headlines is queued and applied by the next update, which takes about 5 minutes. "Run scan now" takes about 15. The status bar shows when an update is running and offers a reload when new data is ready.
- **Paper trading is off.** It needs instant order handling.
- **No second-by-second activity feed.** The status bar shows the update's progress instead.
- **Read state of alerts** is remembered per browser.

## Setup (about 15 minutes, then a 20 to 25 minute first run)

You need a GitHub account (you have one) and a Vercel account.

### 1. Create a Vercel token

1. Sign up at [vercel.com](https://vercel.com) with GitHub. Choose the free Hobby plan.
2. Open **Account Settings** → **Tokens** → **Create**. Name it `oalgo2`, scope your personal account, and choose the longest expiry offered.
3. Copy the token. You will paste it in step 4.

You do not create a Vercel project yourself: the first update creates one called `oalgo2`. Do not import the repository into Vercel either, because that would publish a copy without data.

### 2. Create a GitHub token for the dashboard

The dashboard uses this token to queue your changes and start an update.

1. GitHub → your picture → **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens** → **Generate new token**.
2. Name `oalgo2 dashboard`, expiry up to one year (write the date down; see "Every year" below).
3. **Repository access**: Only select repositories → `oalgo2`.
4. **Permissions** → Repository permissions: **Actions**: Read and write, **Contents**: Read and write. Leave everything else at No access.
5. Generate and copy it.

### 3. Create your master secret

```bash
openssl rand -hex 32
```

This 64-character value encrypts your data and derives the dashboard's other keys. **Keep a copy somewhere safe**, such as a password manager. If it is lost or changed, the saved data cannot be decrypted and the platform starts over from an empty database.

No `openssl`? Any password manager can generate a random string of 40 or more characters instead.

### 4. Add five repository secrets

In the `oalgo2` repository: **Settings** → **Secrets and variables** → **Actions** → **New repository secret**, five times:

| Name | Value |
|---|---|
| `OALGO_SECRET` | the master secret from step 3 |
| `VERCEL_TOKEN` | the token from step 1 |
| `DASHBOARD_GH_TOKEN` | the token from step 2 |
| `APP_PASSWORD` | the password you will sign in with; make it long |
| `OALGO_SEC_USER_AGENT` | your name and an email, for example `Jane Doe jane@example.com` (the SEC asks automated tools to identify themselves) |

Secrets are never shown in logs, not even to you.

### 5. Run the first update

1. Open the repository's **Actions** tab. If GitHub asks whether to enable workflows, enable them.
2. Choose **Update** on the left → **Run workflow** → **Run workflow**.
3. The first run takes 20 to 25 minutes: it installs everything, downloads the FinBERT model, scans and publishes.
4. When it finishes, its summary shows the dashboard's address. The permanent one is in Vercel under the `oalgo2` project → **Domains**, usually `https://oalgo2.vercel.app` or similar.

### 6. Use it

1. Open the address and sign in with `APP_PASSWORD`.
2. Add your holdings under **My portfolio** (or import a CSV). They appear after the next update, about 5 minutes later.
3. From then on it updates by itself every weekday evening, plus whenever you change something.

## Day to day

| To | Do |
|---|---|
| Change the password | Edit the `APP_PASSWORD` secret, then run **Update** once. Changing `OALGO_SECRET` is not the way: it would lose your data. |
| See whether a change was applied | **Scans and data** → "Recent changes from the dashboard" lists each one, with the reason if it was refused. |
| Force a fresh scan | **Command** → **Run scan now**, or run **Update** from the Actions tab. |
| Check what failed | The Actions tab shows each run. Logs only say which step failed, on purpose. |

**Every year**: when the GitHub token from step 2 expires, the dashboard can no longer queue changes. Create a new one the same way and replace the `DASHBOARD_GH_TOKEN` secret. The Vercel token may expire too; replace `VERCEL_TOKEN` the same way.

## Limits of the free services

- **GitHub pauses scheduled runs after 60 days without activity in the repository.** If the daily update stops, open the Actions tab and re-enable it. Changes you make on the dashboard still start updates either way.
- **Saved data.** The encrypted state is kept in the Actions cache and backed up to a release called `oalgo-state` (marked "do not delete"). The cache drops anything unused for 7 days; the release copy does not expire.
- **Vercel's Hobby plan is for personal, non-commercial use.**
- **Update length.** A run is capped at 75 minutes. Scanning far more than 300 stocks may hit it; raise the scan size gradually.

## Removing it

Delete the `oalgo2` project in Vercel, the five repository secrets, the `oalgo-state` release and the `oalgo-queue` branch.

## Optional: instant updates on a paid server

If you later want instant changes, live activity and paper trading online, the repository also contains a paid setup: the research engine on Render with a disk (`render.yaml`, about $25 a month for the 2 GB plan FinBERT needs), with the dashboard on Vercel relaying to it (`BACKEND_URL` and `BACKEND_API_KEY`). The dashboard code supports both; the free setup above is the default.
