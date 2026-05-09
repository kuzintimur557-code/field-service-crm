from fastapi import APIRouter

router = APIRouter()

users = {
    "boss": {
        "password":"1234",
        "role":"boss"
    },

    "manager": {
        "password":"1234",
        "role":"manager"
    },

    "ivan": {
        "password":"1234",
        "role":"worker"
    },

    "oleg": {
        "password":"1234",
        "role":"worker"
    }
}


@router.post("/login")
def login(username: str, password: str):

    user = users.get(username)

    if not user:
        return {
            "error":"user not found"
        }

    if user["password"] != password:
        return {
            "error":"wrong password"
        }

    return {
        "ok":True,
        "role": user["role"]
    }