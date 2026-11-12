# Putting Scout online

Same shape as Relay: the **API** on Google Cloud Run, the **page** on Vercel.

## 1. The tables and the sample run (once, from your computer)

```powershell
python -m scout.db          # creates the "scout" tables in Supabase
python -m scout.prepare     # researches the 38 tested businesses from the saved snapshot (no Tavily credits, ~6 min)
```

## 2. The API on Cloud Run

```powershell
copy deploy.env.example.yaml deploy.env.yaml
notepad deploy.env.yaml          # DATABASE_URL, GROQ_API_KEY, TAVILY_API_KEY: the same values as in .env
gcloud run deploy scout --source . --region us-west1 --allow-unauthenticated `
  --memory 512Mi --cpu 1 --min-instances 0 --max-instances 1 --concurrency 20 --timeout 120 `
  --no-cpu-throttling --cpu-boost --env-vars-file deploy.env.yaml
```
Check `<Service URL>/health` says `"status":"ok"`.

| Option | Why |
| --- | --- |
| `--no-cpu-throttling` | Runs keep researching in the background after the page gets its answer; without this, Cloud Run pauses them. |
| `--max-instances 1` | One server keeps the rate limits (runs per hour, businesses per day) in one place. |
| `--min-instances 0` | Free when idle. A run in progress keeps the server awake until it finishes. |

## 3. The page on Vercel

1. Push the repo to GitHub.
2. Vercel → **Add New → Project** → import `scout` → **Root Directory** `web`.
3. **Environment Variables**: `NEXT_PUBLIC_API_URL` = the Cloud Run URL (no `/` at the end).
4. **Deploy**.

## 4. Let the page call the API

In `deploy.env.yaml`: `ALLOWED_ORIGINS: "https://YOUR-SCOUT.vercel.app,http://localhost:3000"`, then run the
`gcloud run deploy` command again. `<API URL>/health` lists the allowed addresses.

## If something's wrong

| What you see | Likely cause |
| --- | --- |
| "Couldn't reach Scout's server" | `/health` doesn't list the page's exact address, or `NEXT_PUBLIC_API_URL` is wrong on Vercel. |
| No sample run | Step 1 wasn't run. |
| A lead says "Interrupted by a server restart" | The server restarted mid-run (a new deploy); start the run again. |
| "Tavily's monthly credits… used up" | The free plan's 1,000 credits are spent; they reset monthly. |
| Logs | `gcloud run services logs read scout --region us-west1 --limit 50` |
