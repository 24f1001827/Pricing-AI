from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Literal
from datetime import datetime
import re

class ColumnMapping(BaseModel):
    pricing_column: str
    demand_column: str
    date_column: str
    other_columns: List[str] = []

class CSVValidationResult(BaseModel):
    is_relevant: bool
    reason: str
    column_mapping: Optional[ColumnMapping] = None

class CriticReview(BaseModel):
    approved: bool
    restart_from: Optional[Literal["eda", "feature_engineering", "train_model"]] = None
    eda_feedback: Optional[str] = None
    feature_engineering_feedback: Optional[str] = None
    model_training_feedback: Optional[str] = None

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage] = []

class StructuredTrainingDataset(BaseModel):
    unique_id: str
    rows: int
    message: str


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        email = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            raise ValueError("Enter a valid email address")
        return email


class RegisterRequest(LoginRequest):
    name: str = Field(min_length=2, max_length=100)
