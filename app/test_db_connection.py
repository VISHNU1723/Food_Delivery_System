
from sqlalchemy import text
from database import engine

try:
    with engine.connect() as connection:
        result = connection.execute(text("SELECT DATABASE(), CURRENT_USER()"))
        print("MySQL connection successful!")
        print("Database and user:", result.fetchone())
except Exception as error:
    print("MySQL connection failed.")
    print(error)
