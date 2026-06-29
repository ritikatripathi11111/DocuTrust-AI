"""Clients router: CRUD for client profiles (MongoDB)."""
from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, HTTPException

from bson import ObjectId
from app.core.mongodb_client import get_database
from app.models.schemas import ClientCreate, ClientOut, ClientUpdate

router = APIRouter(prefix="/api/clients", tags=["clients"])


@router.post("", response_model=ClientOut)
def create_client(payload: ClientCreate):
    try:
        db = get_database()

        data = payload.model_dump()
        data["created_at"] = datetime.utcnow()

        result = db.clients.insert_one(data)

        data["id"] = str(result.inserted_id)

        return ClientOut(**data)

    except Exception as e:
        import traceback
        traceback.print_exc()
        print("ERROR:", repr(e))
        raise

@router.get("", response_model=list[ClientOut])
def list_clients():
    try:
        print("LIST CLIENTS CALLED")

        db = get_database()

        docs = list(db.clients.find())
        print(docs)

        rows = []

        for doc in docs:
            doc["id"] = str(doc["_id"])
            doc.pop("_id", None)
            
            if "created_at" not in doc:
                doc["created_at"] = datetime.utcnow()
            rows.append(ClientOut(**doc))
        return rows

    except Exception as e:
        import traceback
        traceback.print_exc()
        print("ERROR:", repr(e))
        raise

@router.get("/{client_id}", response_model=ClientOut)
def get_client(client_id: str):

    db = get_database()

    doc = db.clients.find_one({"_id": ObjectId(client_id)})

    if not doc:
        raise HTTPException(status_code=404, detail="Client not found")

    doc["id"] = str(doc["_id"])
    doc.pop("_id", None)

    return ClientOut(**doc)

@router.put("/{client_id}", response_model=ClientOut)
def update_client(client_id: str, payload: ClientUpdate):

    db = get_database()

    values = {
        k: v
        for k, v in payload.model_dump().items()
        if v is not None
    }

    if not values:
        raise HTTPException(status_code=400, detail="no fields to update")

    result = db.clients.update_one(
        {"_id": ObjectId(client_id)},
        {"$set": values},
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="client not found")

    doc = db.clients.find_one({"_id": ObjectId(client_id)})

    doc["id"] = str(doc["_id"])
    doc.pop("_id", None)

    return ClientOut(**doc)

@router.delete("/{client_id}")
def delete_client(client_id: str):

    db = get_database()

    result = db.clients.delete_one(
        {"_id": ObjectId(client_id)}
    )

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="client not found")

    return {
        "status": "deleted",
        "id": client_id,
    }
