from fastapi import APIRouter
from fastapi import UploadFile
from fastapi import File

from pydantic import BaseModel

import shutil
import uuid
import os

router = APIRouter()

UPLOAD_DIR = "uploads"

os.makedirs(UPLOAD_DIR, exist_ok=True)

tasks_db = []

files_db = {}

comments_db = {}


class TaskCreate(BaseModel):
    client_name: str
    phone: str
    address: str
    description: str
    worker: str
    scheduled_date: str


class TaskUpdate(BaseModel):
    client_name: str
    phone: str
    address: str
    description: str
    worker: str
    scheduled_date: str


class CommentCreate(BaseModel):
    text: str


@router.post("/tasks")
def create_task(task: TaskCreate):

    new_task = {
        "id": len(tasks_db) + 1,
        "client_name": task.client_name,
        "phone": task.phone,
        "address": task.address,
        "description": task.description,
        "assigned_to": task.worker,
        "scheduled_date": task.scheduled_date,
        "status": "new"
    }

    tasks_db.append(new_task)

    return {
        "ok": True,
        "task": new_task
    }


@router.put("/tasks/{task_id}")
def update_task(task_id: int, task: TaskUpdate):

    for t in tasks_db:

        if t["id"] == task_id:

            t["client_name"] = task.client_name
            t["phone"] = task.phone
            t["address"] = task.address
            t["description"] = task.description
            t["assigned_to"] = task.worker
            t["scheduled_date"] = task.scheduled_date

            return {
                "ok": True
            }

    return {
        "error": "task not found"
    }


@router.get("/tasks")
def get_tasks():
    return tasks_db


@router.get("/tasks/worker/{worker_name}")
def get_worker_tasks(worker_name: str):

    result = []

    for task in tasks_db:

        if task["assigned_to"] == worker_name:
            result.append(task)

    return result


@router.post("/tasks/{task_id}/upload")
def upload_file(task_id: int, file: UploadFile = File(...)):

    ext = file.filename.split(".")[-1]

    filename = f"task_{task_id}_{uuid.uuid4().hex}.{ext}"

    path = f"{UPLOAD_DIR}/{filename}"

    with open(path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    if task_id not in files_db:
        files_db[task_id] = []

    files_db[task_id].append({
        "name": file.filename,
        "url": f"/uploads/{filename}"
    })

    return {
        "ok": True
    }


@router.get("/tasks/{task_id}/files")
def get_files(task_id: int):

    if task_id not in files_db:
        return []

    return files_db[task_id]


@router.post("/tasks/{task_id}/comments")
def add_comment(task_id: int, comment: CommentCreate):

    if task_id not in comments_db:
        comments_db[task_id] = []

    comments_db[task_id].append({
        "text": comment.text
    })

    return {
        "ok": True
    }


@router.get("/tasks/{task_id}/comments")
def get_comments(task_id: int):

    if task_id not in comments_db:
        return []

    return comments_db[task_id]


@router.post("/tasks/{task_id}/status/{status}")
def update_status(task_id: int, status: str):

    for task in tasks_db:

        if task["id"] == task_id:

            task["status"] = status

            return {
                "ok": True
            }

    return {
        "error": "task not found"
    }