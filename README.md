# Food Delivery System

A backend food delivery application built with FastAPI, SQLAlchemy, MySQL, JWT authentication, and WebSockets.

## Features

- User authentication and role-based access control
- Customer, restaurant, and menu management
- Cart, orders, order items, and payment management
- Coupons and discount handling
- Delivery partner assignment and location tracking
- Live order updates using WebSockets
- Scheduled jobs for order and delivery management
- Restaurant ratings and reviews
- Reports and dashboards for administrators, restaurant owners, and delivery partners

## Technology Stack

- Python
- FastAPI
- SQLAlchemy
- MySQL
- Alembic
- JWT authentication
- Uvicorn
- WebSockets
- APScheduler
- Swagger UI

## Setup Instructions

### 1. Clone the repository

```bash
git clone YOUR_GITHUB_REPOSITORY_URL
cd Food_Delivery_System
```

### 2. Create and activate a virtual environment

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

If `requirements.txt` exists:

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file and configure your MySQL database URL and JWT secret according to the project's settings.

**Never commit `.env` or real credentials to GitHub.**

### 5. Run database migrations

```bash
alembic upgrade head
```

### 6. Start the application

```bash
python -m uvicorn app.main:app --reload
```

### 7. Open Swagger UI

Visit:

http://127.0.0.1:8000/docs

## Testing

Use Swagger UI to test the authentication, restaurant, menu, cart, order, payment, coupon, delivery, rating, and reporting endpoints.

For protected endpoints, log in through `/auth/login` and authorize Swagger with the returned bearer token.

### WebSocket Testing

1. Start the FastAPI server.
2. Open the project's tracking test page, if included.
3. Connect using a valid order ID.
4. Update the delivery partner's location.
5. Verify that live order-tracking events are received.

## Alembic Commands

Create a migration:

```bash
alembic revision --autogenerate -m "describe your changes"
```

Apply migrations:

```bash
alembic upgrade head
```

View migration history:

```bash
alembic history
```

## Test Accounts

Use the test accounts created in your local database. Do not publish personal passwords or production credentials.

Document the username, test password, role, sample restaurant IDs, partner locations, coupon codes, and assumptions here only when they are safe for a public repository.

## Screenshots

Store Swagger API test screenshots and live order-tracking screenshots in the project's `screenshots/` directory.

## Notes

- A running MySQL instance is required.
- Database credentials and JWT secrets must be configured locally.
- API responses depend on the records in the database.
- Some reporting endpoints return empty results when no matching orders or deliveries exist.
