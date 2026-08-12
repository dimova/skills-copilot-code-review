from datetime import date, datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from ..database import announcements_collection, teachers_collection

router = APIRouter(prefix="/announcements", tags=["announcements"])


class AnnouncementPayload(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    message: str = Field(..., min_length=1, max_length=500)
    start_date: Optional[str] = None
    expires_at: str = Field(..., min_length=1)

    @field_validator("expires_at")
    @classmethod
    def validate_expiration_date(cls, value: str) -> str:
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("expires_at must be a valid ISO date") from exc
        return value

    @field_validator("start_date")
    @classmethod
    def validate_start_date(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("start_date must be a valid ISO date when provided") from exc
        return value


class AnnouncementUpdatePayload(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=120)
    message: Optional[str] = Field(default=None, min_length=1, max_length=500)
    start_date: Optional[str] = None
    expires_at: Optional[str] = None

    @field_validator("expires_at")
    @classmethod
    def validate_expiration_date(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("expires_at must be a valid ISO date when provided") from exc
        return value

    @field_validator("start_date")
    @classmethod
    def validate_start_date(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("start_date must be a valid ISO date when provided") from exc
        return value


def _serialize_announcement(item: Dict[str, Any]) -> Dict[str, Any]:
    serialized = dict(item)
    serialized["id"] = str(serialized.pop("_id"))
    if "start_date" in serialized and serialized["start_date"] is not None:
        serialized["start_date"] = str(serialized["start_date"])
    if serialized.get("expires_at") is not None:
        serialized["expires_at"] = str(serialized["expires_at"])
    if "created_at" in serialized and serialized["created_at"] is not None:
        serialized["created_at"] = str(serialized["created_at"])
    return serialized


def _ensure_teacher(username: Optional[str]) -> Dict[str, Any]:
    if not username:
        raise HTTPException(status_code=401, detail="Authentication required for this action")

    teacher = teachers_collection.find_one({"_id": username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")
    return teacher


@router.get("", response_model=List[Dict[str, Any]])
@router.get("/", response_model=List[Dict[str, Any]])
def list_announcements() -> List[Dict[str, Any]]:
    announcements = []
    for announcement in announcements_collection.find().sort("expires_at", 1):
        announcements.append(_serialize_announcement(announcement))
    return announcements


@router.get("/active", response_model=List[Dict[str, Any]])
def list_active_announcements() -> List[Dict[str, Any]]:
    today = date.today().isoformat()
    announcements = []
    for announcement in announcements_collection.find({
        "expires_at": {"$gte": today},
        "$or": [
            {"start_date": {"$exists": False}},
            {"start_date": None},
            {"start_date": {"$lte": today}} 
        ]
    }).sort("expires_at", 1):
        announcements.append(_serialize_announcement(announcement))
    return announcements


@router.post("", response_model=Dict[str, Any])
def create_announcement(payload: AnnouncementPayload, teacher_username: str = Query(...)) -> Dict[str, Any]:
    _ensure_teacher(teacher_username)

    if not payload.expires_at:
        raise HTTPException(status_code=400, detail="Announcement expiration date is required")

    announcement_id = f"announcement-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
    doc = {
        "_id": announcement_id,
        "title": payload.title.strip(),
        "message": payload.message.strip(),
        "start_date": payload.start_date.strip() if payload.start_date else None,
        "expires_at": payload.expires_at,
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }

    announcements_collection.insert_one(doc)
    return _serialize_announcement(doc)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    payload: AnnouncementUpdatePayload,
    teacher_username: str = Query(...),
) -> Dict[str, Any]:
    _ensure_teacher(teacher_username)

    existing = announcements_collection.find_one({"_id": announcement_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Announcement not found")

    update_data: Dict[str, Any] = {}
    if payload.title is not None:
        update_data["title"] = payload.title.strip()
    if payload.message is not None:
        update_data["message"] = payload.message.strip()
    if payload.start_date is not None:
        update_data["start_date"] = payload.start_date.strip() if payload.start_date else None
    if payload.expires_at is not None:
        update_data["expires_at"] = payload.expires_at

    if not update_data.get("expires_at") and not existing.get("expires_at"):
        raise HTTPException(status_code=400, detail="Announcement expiration date is required")

    if "expires_at" in update_data and not update_data["expires_at"]:
        raise HTTPException(status_code=400, detail="Announcement expiration date is required")

    if update_data:
        announcements_collection.update_one({"_id": announcement_id}, {"$set": update_data})

    updated = announcements_collection.find_one({"_id": announcement_id})
    if not updated:
        raise HTTPException(status_code=404, detail="Announcement not found")
    return _serialize_announcement(updated)


@router.delete("/{announcement_id}", response_model=Dict[str, str])
def delete_announcement(announcement_id: str, teacher_username: str = Query(...)) -> Dict[str, str]:
    _ensure_teacher(teacher_username)

    result = announcements_collection.delete_one({"_id": announcement_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")
    return {"message": "Announcement deleted successfully"}
