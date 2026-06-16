from fastapi import FastAPI
from backend.database import engine, Base
from sqlalchemy import text

app = FastAPI()

Base.metadata.create_all(bind=engine)

@app.get("/")
def root():
    return {"status":"running"}

@app.get("/db-test")
def db_test():
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            return {
                "database": "connected",
                "result": result.scalar()
            }
    except Exception as e:
        return {
            "database": "failed",
            "error": str(e)
        }
    
@app.get("/tables")
def get_tables():
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SHOW TABLES"))
            tables = [row[0] for row in result.fetchall()]
            return {"tables": tables}
    except Exception as e:
        return {"error": str(e)}