# TimePilot AI Backend - Student Explanation Script

Use this script to explain the `timepilot-backend` folder to a student.

## 1. Big Picture

This backend is the server side of TimePilot AI.

The frontend is the website or dashboard that the user sees. The backend is the brain behind it. It handles login, stores data in the database, creates schedules, tracks expenses, talks to Gemini AI, sends Telegram reminders, and gives data back to the frontend through API endpoints.

The backend is built using FastAPI, which is a Python framework for creating APIs.

The main technologies used here are:

- FastAPI for API routes
- SQLAlchemy for database models and queries
- MySQL for storing data
- JWT tokens for authentication
- OTP login for phone-based sign in
- Gemini AI for parsing schedule and expense messages
- APScheduler for background reminder jobs
- Telegram bot integration for sending messages

## 2. Root Backend Folder

Inside `timepilot-backend`, we mainly have:

- `backend/`
- `scripts/`
- `requirements.txt`
- `Procfile`

`backend/` contains the actual application code.

`scripts/` contains helper scripts used for maintenance.

`requirements.txt` lists all Python packages needed to run the backend.

`Procfile` tells Railway or a similar hosting platform how to start the backend server.

## 3. requirements.txt

Explain it like this:

This file is like a shopping list for Python. When we install the project, Python reads this file and installs packages like FastAPI, SQLAlchemy, PyMySQL, JWT tools, Gemini AI SDK, and APScheduler.

Important packages:

- `fastapi`: creates API endpoints
- `uvicorn`: runs the FastAPI server
- `sqlalchemy`: talks to the database using Python classes
- `pymysql`: connects SQLAlchemy to MySQL
- `python-dotenv`: reads values from `.env`
- `python-jose`: creates and verifies JWT tokens
- `passlib`: password or security helper library
- `google-generativeai`: connects to Gemini
- `apscheduler`: runs background scheduled jobs

## 4. Procfile

Explain it like this:

The `Procfile` is used during deployment. It tells the hosting service what command should start the app.

For this project, it starts the FastAPI app using Uvicorn and points to:

`backend.main:app`

That means:

- open the `backend/main.py` file
- find the variable called `app`
- run it as the FastAPI application

## 5. backend/main.py

This is the entry point of the backend.

Explain it like this:

When the server starts, this file creates the FastAPI app, connects all routers, creates database tables, starts the scheduler, and sets up CORS.

Main responsibilities:

- Creates the FastAPI app
- Imports all database models
- Calls `Base.metadata.create_all(bind=engine)` to create missing tables
- Starts background jobs using `start_scheduler()`
- Registers API route files like auth, events, expenses, analytics, and AI
- Provides health-check routes like `/`, `/db-test`, `/tables`, and `/schema-check`

Important idea:

`main.py` is like the reception desk of the backend. Every request first enters the FastAPI app, then gets sent to the correct router.

## 6. backend/database.py

This file sets up the database connection.

Explain it like this:

The backend needs to store users, events, expenses, budgets, sessions, and other records. To do that, it connects to a MySQL database.

This file:

- Loads environment variables
- Reads `DATABASE_URL`
- Creates a SQLAlchemy database engine
- Creates `SessionLocal`, which is used to talk to the database
- Creates `Base`, which all model classes inherit from

Simple explanation:

`engine` is the actual database connection.

`SessionLocal` is like a temporary conversation with the database.

`Base` is the parent class for all database tables.

## 7. backend/core/

The `core` folder contains common backend configuration and shared dependencies.

### backend/core/config.py

This file defines all environment-based settings.

It reads values such as:

- `DATABASE_URL`
- `JWT_SECRET`
- `JWT_ALGORITHM`
- `TELEGRAM_BOT_TOKEN`
- `GEMINI_API_KEY`
- `DEBUG`

Explain it like this:

Instead of hardcoding secret values in the code, we keep them in environment variables. `config.py` reads those values and makes them available to the app.

### backend/core/dependencies.py

This file contains reusable FastAPI dependencies.

Main functions:

- `get_db()`: creates and closes database sessions for each request
- `get_current_user()`: checks the JWT token and returns the logged-in user

Explain it like this:

Whenever an API endpoint needs the database, it uses `get_db`.

Whenever an API endpoint should only work for logged-in users, it uses `get_current_user`.

## 8. backend/models/

The `models` folder defines database tables using SQLAlchemy.

Each model class represents one table.

Examples:

- `user.py`: stores user information
- `session.py`: stores login sessions and refresh tokens
- `otp_verification.py`: stores OTP codes
- `telegram_account.py`: stores Telegram connection details
- `event.py`: stores schedules, tasks, meetings, reminders
- `notification.py`: stores reminder notifications
- `expense.py`: stores expenses and budget limits
- `activity_log.py`: stores user activity
- `recommendation.py`: stores AI recommendations and insights
- `streak.py`: stores productivity or expense logging streaks

Explain it like this:

Models are the database blueprint. If the database is a set of tables, models describe what columns each table has.

Example:

The `Event` model has columns like:

- `id`
- `user_id`
- `title`
- `description`
- `event_type`
- `start_datetime`
- `end_datetime`
- `status`
- `created_at`
- `updated_at`

This means every event in the database will store these pieces of information.

## 9. backend/schemas/

The `schemas` folder defines request and response shapes using Pydantic.

Explain it like this:

Models are for the database.

Schemas are for the API.

When the frontend sends data to the backend, schemas validate that the data is correct. When the backend sends data back, schemas help shape the response.

Examples:

- `auth.py`: login, OTP, refresh-token request formats
- `event.py`: event create, update, parse, and response formats
- `expense.py`: expense and budget formats
- `analytics.py`: analytics, insights, recommendations, streak responses
- `overview.py`: dashboard overview response
- `response.py`: common success/error response wrapper
- `user.py`: user output format

Example explanation:

If the frontend creates an event, it must send fields like `title`, `event_type`, and `start_datetime`. The schema checks that those fields are valid before the service saves anything.

## 10. backend/api/

The `api` folder contains the FastAPI route files.

Each file groups related API endpoints.

Examples:

- `auth.py`: login and user profile endpoints
- `events.py`: event CRUD endpoints
- `schedule.py`: natural-language schedule parsing and confirmation
- `expenses.py`: expense CRUD and expense parsing
- `budget.py`: budget limits and budget alerts
- `overview.py`: dashboard summary data
- `analytics.py`: daily, weekly, monthly analytics
- `ai.py`: recommendations, insights, and streaks
- `telegram.py`: Telegram connection/webhook endpoints

Explain it like this:

API files are the doors of the backend. Each URL endpoint is a door. The frontend knocks on a door, and the backend responds.

Example flow for events:

- `POST /events`: create a new event
- `GET /events`: list all events
- `GET /events/{id}`: get one event
- `PUT /events/{id}`: update an event
- `DELETE /events/{id}`: delete an event

## 11. backend/services/

The `services` folder contains business logic.

Explain it like this:

API files should stay simple. They receive the request and call the service. The service decides what should happen.

Examples:

- `auth_service.py`: handles OTP login and token creation
- `otp_service.py`: creates and verifies OTP codes
- `otp_provider.py`: sends or simulates OTP delivery
- `jwt_service.py`: creates and verifies JWT tokens
- `event_service.py`: event business logic
- `expense_service.py`: expense and budget logic
- `analytics_service.py`: productivity and spending analytics
- `ai_service.py`: AI recommendations and insights
- `streak_service.py`: productivity streak handling
- `gemini_schedule_parser.py`: uses Gemini to parse schedule text
- `gemini_expense_parser.py`: uses Gemini to parse expense text

Important teaching line:

The service layer is where the app's rules live.

For example, when creating an event:

1. API receives the request
2. Schema validates the data
3. Service checks the business logic
4. Repository saves it to the database

## 12. backend/repositories/

The `repositories` folder contains database query logic.

Explain it like this:

Repositories are responsible for talking directly to the database.

Examples:

- `user_repository.py`: find users by ID or phone number
- `session_repository.py`: create and delete login sessions
- `event_repository.py`: create, list, update, and delete events
- `expense_repository.py`: create, list, update, and delete expenses and budgets
- `analytics_repository.py`: query data for analytics and streaks

Important idea:

Services should not write complex database queries directly. They ask repositories to do that.

This keeps the project organized.

## 13. backend/providers/

The `providers` folder contains external service integrations.

Right now, it has Telegram support.

Files:

- `providers/telegram/base.py`
- `providers/telegram/telegram_provider.py`

Explain it like this:

A provider is code that connects our app to an outside platform. In this project, the Telegram provider sends messages through the Telegram Bot API.

The scheduler and Telegram API routes can use this provider to send reminders or daily briefings.

## 14. backend/scheduler/

The `scheduler` folder contains background jobs.

Main file:

- `scheduler.py`

Explain it like this:

Normal API endpoints only run when a user makes a request. But reminders must happen automatically, even if the user is not clicking anything.

That is why this project uses APScheduler.

The scheduler has jobs like:

- Check every minute for due notifications
- Send Telegram reminders
- Send daily briefings at a fixed time

Example:

If a user has a meeting at 10:00 AM and a reminder is stored in the database, the scheduler checks when the reminder time arrives, sends a Telegram message, and marks it as sent.

## 15. backend/database/

This folder contains another database-related module:

- `session.py`

It appears to duplicate or support database session setup. The main project is currently using `backend/database.py` for `Base`, `engine`, and `SessionLocal`.

Explain it like this:

Sometimes projects evolve and may contain older or alternate database setup files. The important thing is to check which one is imported by the rest of the app.

In this project, many files import from:

`backend.database`

So `backend/database.py` is the main one.

## 16. backend/routes/

This folder currently only has:

- `__init__.py`

It does not contain active route files right now.

Explain it like this:

This may be a placeholder folder. The actual routes are inside the `backend/api/` folder.

## 17. scripts/

The `scripts` folder contains maintenance scripts.

Important file:

- `reset_auth_tables.py`

Explain it like this:

This script is used when authentication tables have schema problems. It can reset auth-related database tables so the database matches the current models.

This is not part of normal app runtime. It is an admin/developer utility.

## 18. Request Flow Example: Login

Now explain a full flow.

When a user logs in with phone number and OTP:

1. Frontend calls `POST /auth/send-otp`
2. `backend/api/auth.py` receives the request
3. It calls `AuthService.send_otp`
4. `AuthService` uses `OTPService`
5. OTP is stored in the `otp_verifications` table
6. User enters OTP
7. Frontend calls `POST /auth/verify-otp`
8. Backend checks OTP
9. Backend creates or finds the user
10. Backend creates access and refresh tokens
11. Backend stores the session
12. Frontend uses the access token for future protected API calls

Simple student explanation:

The OTP proves the phone number belongs to the user. The JWT token proves the user is logged in for future requests.

## 19. Request Flow Example: Creating an Event

When a user creates an event:

1. Frontend calls `POST /events`
2. `backend/api/events.py` receives the request
3. `EventCreate` schema validates the request body
4. `get_current_user()` checks the JWT token
5. `EventService.create_event()` runs business logic
6. `EventRepository.create()` saves the event in the database
7. Backend returns the created event to the frontend

Teaching line:

This is a clean layered architecture:

API -> Schema -> Service -> Repository -> Model -> Database

## 20. Request Flow Example: AI Schedule Parsing

When a user types something like:

`Meeting with Rahul tomorrow at 4 PM`

The flow is:

1. Frontend calls `POST /schedule/parse`
2. Backend sends the message to Gemini
3. Gemini returns structured data such as title, date, time, and type
4. Frontend shows the parsed result to the user
5. User confirms
6. Frontend calls `POST /schedule/confirm`
7. Backend saves it as an event

Simple explanation:

Gemini helps convert natural language into structured data that the database can store.

## 21. Request Flow Example: Expense Tracking

When a user logs an expense:

1. Frontend calls `POST /expenses`
2. Backend validates the expense data
3. Expense service applies business logic
4. Expense repository saves it
5. Budget endpoints can later compare spending against monthly limits

If the user types a natural sentence like:

`Spent 250 on lunch today`

Then:

1. Frontend calls `POST /expenses/parse`
2. Gemini extracts amount, category, date, and description
3. User can confirm and save it

## 22. Why This Folder Structure Is Good

This project separates responsibilities well:

- `api/` handles HTTP requests
- `schemas/` validates request and response data
- `services/` handles business rules
- `repositories/` handles database queries
- `models/` defines database tables
- `providers/` talks to external services
- `scheduler/` runs background jobs
- `core/` stores shared config and dependencies

This makes the code easier to understand, test, and modify.

## 23. Simple Analogy

You can explain the backend like a college office:

- API routes are reception counters
- Schemas are forms that check if details are filled correctly
- Services are staff members who know the rules
- Repositories are clerks who access the records room
- Models are the format of records
- Database is the records room
- Providers are outside services like Telegram
- Scheduler is the alarm system that reminds staff to do work on time

## 24. Final Summary For Students

TimePilot AI backend is a FastAPI application that manages users, schedules, expenses, budgets, analytics, AI insights, and Telegram reminders.

The most important idea is layered architecture.

When a request comes in, it usually moves like this:

`Frontend -> API -> Schema -> Service -> Repository -> Database`

And the response goes back:

`Database -> Repository -> Service -> API -> Frontend`

Once students understand this flow, the folder structure becomes much easier to understand.

