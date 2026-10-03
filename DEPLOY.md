# Putting StoryForge online

StoryForge needs two things online: the **app** (backend + website in one container) and a
**Postgres database with pgvector**. This guide uses Neon for the database and Render for the
app. Any host that runs Docker and any Postgres with pgvector 0.7 or newer also works.

Time needed: about 20 minutes.

## Before you start

1. **Rotate your NVIDIA API key.** The review found that an old key was shared inside a zip.
   Create a new key at https://build.nvidia.com and delete the old one.
2. **Commit and push everything** to a GitHub repository. Check that `backend/.env` is NOT
   committed (`git status` must not list it; `.gitignore` already excludes it).
3. **Run the tests once locally:** `docker compose up -d`, then in `backend/`:
   `pip install -r requirements-dev.txt` and `pytest`. All tests should pass.

## 1. Create the database (Neon)

1. Sign up at https://neon.tech and create a project (pick the region closest to you; for
   India, Singapore `ap-southeast-1` is closest).
2. Copy the connection string. It looks like
   `postgresql://user:password@ep-something.ap-southeast-1.aws.neon.tech/neondb?sslmode=require`.
3. That's all. The app creates its tables, turns on pgvector and builds the fast search
   index the first time it starts.

## 2. Deploy the app (Render)

1. On https://render.com choose **New → Blueprint** and pick your repository. Render reads
   `render.yaml` and sets up a web service from the `Dockerfile`.
2. When asked, fill in:
   - `NVIDIA_API_KEY`: your new key
   - `DATABASE_URL`: the Neon connection string
   - `INVITE_CODE` (optional): if set, people need this code to create an account
3. Render generates `SECRET_KEY` for you. Sign-in is switched on (`AUTH_REQUIRED=true`).
4. Wait for the build, then open the address Render gives you (for example
   `https://storyforge-xxxx.onrender.com`).
5. Open `https://storyforge-xxxx.onrender.com/health`. You should see
   `"database": true, "ai_configured": true, "auth_required": true`.
6. Create your account on the website. **The first account adopts any books that existed
   before sign-in was switched on.**

## 3. After the first sign-in

- Once your team has accounts, set `ALLOW_REGISTRATION=false` in Render's environment
  settings so nobody else can sign up.
- Each user can check `DAILY_CHAPTER_LIMIT` chapters per day (default 40), because every
  chapter uses requests on your NVIDIA key. Change it in Render's environment settings.
- The website and the API share one address, so no other website may call the API. Only set
  `ALLOWED_ORIGINS` if you build a separate frontend.

## Things to know

- **Plan choice.** Render's free plan sleeps after 15 minutes without visitors; the first
  visit afterwards takes about a minute. A chapter being checked when the service goes to
  sleep or restarts is marked "failed" with a clear message; just add it again. For regular
  use, the Starter plan avoids both.
- **One worker.** Background jobs run inside the web process, so the app must run as ONE
  process (the Dockerfile does this). Don't raise the worker count.
- **Database size.** Each fact stores a 2048-number search vector (about 8 KB). Neon's free
  0.5 GB holds roughly 50,000 facts, which is several novels.
- **NVIDIA limits.** The free NVIDIA tier limits requests per minute. StoryForge paces itself
  (`MAX_REQUESTS_PER_MINUTE`, default 30) and slows down automatically when refused.
- **Backups.** Every book can be downloaded as JSON from the Books page (Export JSON). Neon
  also keeps point-in-time history.

## Run exactly the deployed setup on your own computer

```
docker compose --profile app up --build
```

then open http://localhost:8000. To try it with sign-in switched on, add
`AUTH_REQUIRED=true` and a `SECRET_KEY` to `backend/.env` first.
