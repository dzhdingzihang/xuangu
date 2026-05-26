# Deploy to Render

This app is ready for Render as a Python Web Service.

## 1. Push this folder to GitHub

From this directory:

```bash
git remote add origin https://github.com/<your-user>/chan-stock-selector.git
git push -u origin main
```

## 2. Open Render Blueprint

After the repo is pushed, open:

```text
https://dashboard.render.com/blueprint/new?repo=https://github.com/<your-user>/chan-stock-selector
```

Render will read `render.yaml` and create the Web Service.

## 3. Runtime details

Render service:

- Runtime: Python
- Region: Singapore
- Build command: `pip install -r requirements.txt`
- Start command: `python server.py --host 0.0.0.0 --port $PORT`
- Health check: `/api/status`

## 4. Daily 08:30 refresh

The app has an in-process scheduler for Asia/Shanghai 08:30 on weekdays.

Important: Render Free Web Services can sleep when idle. If the service sleeps at 08:30, the in-process scheduler will not run exactly on time. For reliable scheduled refresh, use one of:

- Render paid always-on instance
- External uptime/cron service that calls `/api/pick?force=1`
- Render Cron Job that calls the public service URL after deployment

## 5. Safety

This is a decision-support tool. It does not guarantee profit. If the model threshold fails, it returns `NO_TRADE`.
