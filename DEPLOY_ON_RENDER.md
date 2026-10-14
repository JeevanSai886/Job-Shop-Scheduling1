# Publish Job-Shop Scheduling on Render (one public link)

This folder is preconfigured to serve BOTH the React UI and Python solver from
ONE Render Web Service. No frontend URL, backend URL, CORS, or separate server
configuration is needed.

## Part 1: Publish this folder to GitHub

1. Extract `Job-Shop-Scheduling-Render-Ready.zip` to your computer.
2. Sign in to GitHub and create a NEW **empty** repository named
   `job-shop-scheduling` (do not generate an extra README or .gitignore).
3. Easiest on Windows: use GitHub Desktop, `File > Add local repository`, select
   the extracted `Job-Shop-Scheduling` folder, choose **Create a repository here**,
   make an initial commit, and click **Publish repository**.
   Alternatively, from VS Code's terminal in the folder use:

   ```powershell
   git init
   git add .
   git commit -m "Prepare job-shop scheduling for cloud"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/job-shop-scheduling.git
   git push -u origin main
   ```

   Create the empty repository first and replace YOUR_USERNAME with your GitHub username.
   Git on your computer must be configured and authenticated.
4. In the GitHub repository homepage, make sure `Dockerfile`, `render.yaml`,
   `backend/`, and `frontend/` all appear together at the repository root.
   Do not upload only the ZIP file itself.

## Part 2: Publish the website

1. Open https://dashboard.render.com/ and sign in with GitHub.
2. Choose `New > Web Service`, connect your GitHub repository, and select it.
3. Set **Language = Docker** (in some versions this is shown as Runtime = Docker).
4. Make sure the Dockerfile path is `./Dockerfile`, and the **Root Directory**
   is empty/the repository root.
5. Pick the **Free** compute plan (if offered), then click `Create Web Service`.
6. Watch the Deploy logs for successful build and startup. Render gives you a
   URL like `https://job-shop-scheduling-demo.onrender.com` (the exact URL can vary).
7. Open the URL, select benchmark `ft06`, and try **Solve schedule**. Visit
   `/api/health` at the same domain to see `{ "status": "ok" }`.

There is also a `render.yaml` Blueprint if you prefer `New > Blueprint` instead
of `New > Web Service`; choose ONE of these methods, not both.

## Important limitations of Render Free

- The free service sleeps after 15 minutes without traffic, and the next visit
  may take approximately one minute to wake up.
- Free services have temporary local storage. This project's SQLite instance
  data, including custom uploads, WILL BE LOST when the service sleeps,
  restarts, or redeploys. Bundled ft06 and ft10 benchmarks remain available.
- Its free compute is just 0.1 CPU and 512 MB RAM; larger MILP/CP-SAT
  optimization runs may be too slow or hit memory limits.
- The original project has no accounts/authentication or user isolation. Use
  this as a project demonstration, not a secure multi-user production system.
- To persist uploads, redesign storage to use a durable database or upgrade
  and attach a persistent disk. A paid compute plan alone is not persistent.

## If you encounter an error

- `Dockerfile not found`: `Dockerfile` must be at repository root.
- `/api` returns 404: verify the server command uses `backend.cloud:app`.
- Build fails: open your Render service > Logs and read the *first* failing line.
- Website opens, but Solve fails: inspect `/api/health`, Render logs, and check
  memory/CPU/time limits.
- If Git asks who you are, configure `git config --global user.name "Your Name"`
  and `git config --global user.email "your-github-email@example.com"`.
