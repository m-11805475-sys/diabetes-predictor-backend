# GlucoGuide shared suggestions backend

This FastAPI service provides a shared SQLite-backed suggestion store for the Diabetes Predictor AI / GlucoGuide website and an export endpoint the CatBoost notebook can read. It is a separate service; it does **not** run or change the diabetes model.

## Endpoints

- `GET /health` — health check
- `GET /api/suggestions` — all shared suggestions as JSON
- `POST /api/suggestions` — submit `{ "category": "Feature idea", "suggestion": "..." }`
- `GET /api/suggestions/export.json` — notebook-compatible JSON download
- `GET /api/suggestions/export.md` — compiled Markdown download
- `GET /docs` — interactive API documentation

Allowed categories: `Feature idea`, `Usability`, `Model or data`, `Bug report`, `Other`. Suggestions are limited to 5,000 characters. A lightweight per-process IP rate limit defaults to 20 submissions/hour. IPs are not stored.

## Run locally

Requires Python 3.10+.

```bash
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/health` and confirm `status` is `ok`. The SQLite database is created at `data/suggestions.db` by default. Set `DATABASE_PATH` to a persistent mounted disk path in production.

## Connect the website

In `diabetes_predictor_preview.html`, set the `API_BASE_URL` constant near the suggestions JavaScript to your backend origin, for example `https://YOUR-SERVICE.example.com` (no trailing slash). For local use it defaults to `http://127.0.0.1:8000`. Host the HTML separately over HTTPS for real users. The backend CORS default is `*` to make setup easy; once deployed, set `CORS_ORIGINS` to your exact website origin(s), comma-separated. Do not use `*` if you later add credentialed/admin endpoints.

## Deploy notes

Deploy the folder as a Docker web service or deploy `app.py` with the command `uvicorn app:app --host 0.0.0.0 --port $PORT`. Configure a persistent disk and set `DATABASE_PATH` to a file on that disk; ephemeral filesystems may lose the database during redeploys. Configure `CORS_ORIGINS` to the website's HTTPS origin. Use HTTPS, backups, monitoring, and a managed database for a larger public launch.

## Notebook sync

The updated notebook cell reads `DIABETES_SUGGESTIONS_API_URL` if set, e.g. `https://YOUR-SERVICE.example.com/api/suggestions/export.json`. Otherwise it imports local `suggestions.json`. The cell downloads the shared suggestions and writes `suggestions_compiled.md`. In hosted notebooks, internet access must be enabled.

## Privacy and safety

The website displays shared suggestions to visitors. Do not collect names, contact details, private medical records, or other sensitive information. Public endpoints can be abused; the included rate limiter is deliberately lightweight and resets on service restart, so put production deployments behind a WAF/reverse proxy or use a managed database/service with stronger abuse protection. Suggestions are product feedback only and must never be treated as diabetes labels or model-training examples.
