# Putting StoryForge online

StoryForge needs two things online: the **app** (backend + website, one container) and a
**Postgres database with pgvector**. Below is a free setup using Neon for the database and
Render for the app. Any host that runs Docker and any Postgres with pgvector will also work.

## 1. Create the database (Neon)
1. Sign up at https://neon.tech and create a project.
2. Copy the connection string. It looks like
   `postgresql://user:password@ep-something.neon.tech/neondb?sslmode=require`.
3. That's it — the app creates its own tables (and turns on pgvector) the first time it starts.

## 2. Deploy the app (Render)
1. Push this repository to GitHub.
2. On https://render.com choose **New → Blueprint** and pick the repository. Render reads
   `render.yaml` and sets up a web service from the `Dockerfile`.
3. When asked, fill in:
   - `NVIDIA_API_KEY` — your key from build.nvidia.com
   - `DATABASE_URL` — the Neon connection string from step 1
4. Wait for the build, then open the address Render gives you
   (e.g. `https://storyforge-xxxx.onrender.com`). The website is at the root address.

## 3. Lock it down (recommended)
- Add `ALLOWED_ORIGINS` with your Render address so other websites can't call your API.
- The app has **no login**. Anyone with the link can read and change the story, and every
  chapter uses your NVIDIA credits. Don't share the link publicly. Adding login is future work.

## Notes
- Render's free plan sleeps after inactivity; the first request afterwards takes ~1 minute.
- To run exactly the deployed setup on your own computer:
  `docker compose --profile app up --build`, then open http://localhost:8000
