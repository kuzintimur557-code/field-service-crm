from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.database import connect

app = FastAPI()

templates = Jinja2Templates(
    directory="app/templates"
)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):

    conn = connect()

    c = conn.cursor()

    c.execute("""
    SELECT *
    FROM tasks
    ORDER BY id DESC
    """)

    tasks = c.fetchall()

    conn.close()

    print(tasks)

    return HTMLResponse(
        "<h1>DEBUG MODE</h1><p>Check railway logs</p>"
    )
