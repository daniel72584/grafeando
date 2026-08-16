from fastapi import FastAPI, Depends

app = FastAPI()

def get_db():
    return "db_session"

@app.get("/users")
def read_users(db = Depends(get_db)):
    return {"users": ["Alice", "Bob"]}
