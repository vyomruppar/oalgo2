# Deploying to the web

The platform has two parts, hosted in two places:

| Part | What it does | Where | Why there |
|---|---|---|---|
| Dashboard (`frontend/`) | Every page you see, the sign-in, and a private relay to the research engine | Vercel | Built for Next.js, free tier is enough |
| Research engine (`backend/`) | Scans, the daily scheduler, the database, news and FinBERT sentiment | Render | Needs an always-on server, a disk and up to 2 GB of memory, which Vercel does not offer |

Your browser only talks to Vercel. The research engine answers nothing except its health check unless the request carries a secret key that only the Vercel server knows, so the dashboard's password is the one lock.

Set up Render first, because Vercel needs two values from it.

## 1. Research engine on Render (about 10 minutes, plus the first build)

1. Sign in at [render.com](https://render.com) with GitHub and allow access to the `oalgo2` repository.
2. Choose **New** → **Blueprint**, pick `vyomruppar/oalgo2`. Render reads `render.yaml` and proposes one service, `oalgo2-api`, with a 5 GB disk.
3. It asks for the values marked "sync: false":
   - `OALGO_SEC_USER_AGENT`: your name and an email address, for example `Jane Doe jane@example.com`. The SEC asks automated clients to identify themselves and may refuse requests without it.
   - The `OALGO_SMTP_*` and `OALGO_ALERT_EMAIL_TO` values only if you want alert e-mails; leave them empty otherwise.
4. Choose **Apply**. The first build takes 5 to 10 minutes because it installs PyTorch for FinBERT.
5. When the service shows **Live**, copy two things from it:
   - its URL, for example `https://oalgo2-api.onrender.com`
   - the value of `OALGO_API_KEY` under **Environment** (Render generated it)

Check it: opening `https://<your-service>.onrender.com/api/health` should show `"status":"ok"`, and `/api/overview` should say "missing or invalid backend key". That second response is correct.

**Cost.** The blueprint uses the **Standard** plan (2 GB memory, needed for FinBERT) plus a 5 GB disk, roughly $25 a month plus about $1.25 for the disk at Render's published prices; check Render's pricing page before applying. To pay less, switch to **Starter** (512 MB) and run without the AI model:
- set `OALGO_SENTIMENT_ENGINE` to `lexicon`
- under **Settings** → **Build**, add the Docker build argument `INSTALL_AI` = `0`

Headlines are then scored with the built-in word list, and the dashboard says so. The free Render plan cannot be used: it has no disk and sleeps when idle, which would lose your data and stop the daily scan.

## 2. Dashboard on Vercel (about 5 minutes)

1. Sign in at [vercel.com](https://vercel.com) with GitHub and allow access to `oalgo2`.
2. **Add New** → **Project** → import `vyomruppar/oalgo2`.
3. Set **Root Directory** to `frontend`. Vercel detects Next.js and reads `frontend/vercel.json`.
4. Under **Environment Variables** add four values:

   | Name | Value |
   |---|---|
   | `BACKEND_URL` | the Render URL from step 1.5, with no trailing slash |
   | `BACKEND_API_KEY` | the `OALGO_API_KEY` value from Render |
   | `APP_PASSWORD` | the password you will sign in with; use a long one |
   | `AUTH_SECRET` | 32 or more random characters; generate them with the command below |

   ```bash
   openssl rand -hex 32
   ```

5. Choose **Deploy**. Vercel gives you an address such as `https://oalgo2.vercel.app`.

The production branch is the repository's default branch, currently `claude/admiring-hypatia-8mav3t`. Every push to it redeploys both services automatically.

## 3. First run

1. Open the Vercel address and sign in with `APP_PASSWORD`.
2. On **Command**, choose **Run scan now**. The first scan verifies listings, downloads prices and SEC filings and scores about 300 stocks; expect around 10 to 15 minutes. The status bar shows its progress.
3. Under **My portfolio**, add the stocks you own, or import them as CSV.
4. After that, a scan runs on its own every weekday at 22:30 UTC.

The hosted copy starts empty. The sample holdings and data from development are not uploaded.

## Changing things later

| To | Do |
|---|---|
| Change the password | Edit `APP_PASSWORD` in Vercel and redeploy. Existing sign-ins stay valid until they expire (30 days) unless you also change `AUTH_SECRET`. |
| Sign everyone out now | Change `AUTH_SECRET` in Vercel and redeploy. |
| Rotate the backend key | Generate a new `OALGO_API_KEY` in Render, paste the same value into `BACKEND_API_KEY` in Vercel, redeploy both. |
| Scan more stocks | Settings → Stocks per scan. More stocks take longer and use more disk. |
| Back up your data | Render → the service → **Disks** → snapshots, or download `/data/oalgo.sqlite` through Render's shell. |

## If something is wrong

| You see | Cause and fix |
|---|---|
| "Cannot reach the research backend" or every panel empty | `BACKEND_URL` is wrong or the Render service is not live. Check the URL and the health check above. |
| 401 errors after signing in | `BACKEND_API_KEY` in Vercel does not match `OALGO_API_KEY` in Render. |
| The sign-in page loops or errors | `AUTH_SECRET` is missing or shorter than 32 characters. |
| Status bar says "Polling every 5s" | Vercel's relay closed the live event stream. Updates still arrive every 5 seconds; nothing is lost. |
| Render runs out of memory | Use the Standard plan, or switch sentiment to the word list as described under Cost. |
