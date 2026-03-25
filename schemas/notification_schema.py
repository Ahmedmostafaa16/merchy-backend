from pydantic import BaseModel, EmailStr, Field


class NotificationCreate(BaseModel):
    email: EmailStr
    threshold_days: int = Field(gt=0)
