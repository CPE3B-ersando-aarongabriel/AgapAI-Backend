# AgapAI Backend

Minimal, professional FastAPI + MongoDB backend scaffold.

## Tech Stack

- FastAPI
- MongoDB (PyMongo)
- Pydantic
- Uvicorn

## Project Structure

```text
app/
	api/
		v1/
			endpoints/
	config/
	core/
	db/
		indexes/
		seeds/
	dependencies/
	exceptions/
	middleware/
	models/
	repositories/
	routes/
	schemas/
	services/
	utils/
	main.py
docs/
scripts/
tests/
	integration/
	unit/
```

## Environment

1. Copy `.env.example` to `.env`.
2. Set your MongoDB connection string in `MONGO_URI`.
3. Set your OpenAI key in `OPENAI_API_KEY`.

## Local Setup

1. Create and activate a virtual environment.
2. Install dependencies:

	 ```bash
	 pip install -r requirements.txt
	 ```

3. Start the API server:

	 ```bash
	 uvicorn app.main:app --reload
	 ```

## Notes

- Keep business logic in `services` and data access in `repositories`.
- Keep request/response contracts in `schemas`.
- Keep MongoDB index and seed assets under `app/db/indexes` and `app/db/seeds`.
