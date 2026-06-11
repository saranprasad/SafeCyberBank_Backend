SAFE CYBER BANK - Flask backend

This app now uses a Flask backend with database persistence.

## Setup

1. Create a virtual environment:
```bash
cd /home/saran/Saran/SAFECYBERBANK
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Set Postgres connection:
```bash
export DATABASE_URL="postgresql://username:password@localhost:5432/your_db_name"
export FLASK_SECRET_KEY="replace-with-a-secret"
```

If `DATABASE_URL` is not set, the app falls back to `sqlite:///safecyberbank.db` for quick local testing.

3. Run the server:
```bash
python server.py
```

4. Open:
```
http://127.0.0.1:5000
```

## Pre-seeded users

- saran / saran2026
- naveen / naveen2026
- prasanna / prasanna2026
- administrator / admin2026

## What changed

- `server.py` is the Flask backend.
- `requirements.txt` defines Flask and SQLAlchemy.
- `app.js` now calls backend API endpoints instead of storing data in browser localStorage.
- `README.md` has backend startup instructions.

