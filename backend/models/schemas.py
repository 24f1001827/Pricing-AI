from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Literal
import re


class TrainingPlan(BaseModel):
    candidate_models: List[
        Literal[
            "hist_gb_monotonic",
            "hist_gb_poisson",
            "ridge_elasticity",
            "random_forest",
            "extra_trees",
        ]
    ] = Field(min_length=1)
    use_log_price: bool = True
    enable_lags: bool = True
    outlier_clip_quantile: Optional[float] = Field(default=0.99, ge=0.9, le=1.0)
    strategy_explanation: str = ""


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: List[ChatMessage] = []


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


class AdminCreateUserRequest(RegisterRequest):
    is_admin: bool = False
