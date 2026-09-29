# Mitalli Bridal World

A polished, mobile-first beauty studio website with:

- FastAPI backend and a static frontend served from one Render web service.
- Deterministic multilingual chatbot powered by spaCy's blank tokenizer and `Matcher`.
- Service prices read from the database instead of being hard-coded into chatbot responses.
- Appointment requests and leads persisted to PostgreSQL on Render, with SQLite fallback for local development.
- Glassmorphism UI with restrained motion, responsive layout, and mobile-friendly CTAs.

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload --port 8000
```

Open `http://localhost:8000`.

The first startup creates the tables and seeds the initial service menu. Update service data through the database or add the admin API before exposing an administrative interface.

## One-click Render Blueprint deployment

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

1. Push this repository to GitHub with `render.yaml` at the repository root.
2. Either click the button above, or in Render choose **New → Blueprint** and select the GitHub repository.
3. Render detects `render.yaml` and creates the Python web service without provisioning a second Postgres database.
4. When Render asks for `DATABASE_URL`, paste the existing database connection string into the protected environment-variable field.
5. Deploy the Blueprint. The web service uses that protected `DATABASE_URL`.

The Blueprint includes:

- Python 3.11.9 pinning.
- Production Gunicorn/Uvicorn start command.
- Render health check at `/healthz`.
- Automatic deploys on commits to the linked GitHub branch.
- A protected `DATABASE_URL` input for reusing an existing Render Postgres database.

Never commit `DATABASE_URL` to GitHub. Set it in Render’s environment variables and rotate the database password if the connection string has been exposed.

For production, update `ALLOWED_ORIGINS`, verify business details, and replace the placeholder gallery treatment with approved business photography.

## Chatbot approach

`backend/app/chatbot.py` uses `spacy.blank("xx")` and `spacy.matcher.Matcher`. It does not download a language model and does not call an AI service. Lowercased phrase patterns cover English, Marathi, and common Marathi-English transliterations, while small regex token patterns catch variants such as `book`, `booking`, and `schedule`.