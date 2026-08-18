from typing import Optional
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END

class AgentState(TypedDict):
    unique_id: str
    file_path: str
    column_mapping: dict
    generated_code: Optional[str]
    execution_result: Optional[dict]
    model_metrics: Optional[dict]
    iteration_count: int
    best_metrics: Optional[dict]
    eda_feedback: Optional[str]
    feature_engineering_feedback: Optional[str]
    model_training_feedback: Optional[str]
    critic_approved: Optional[bool]
    status: str
    error: Optional[str]
    previous_metrics: Optional[dict]
    previous_feature_code: Optional[str]
    engineered_file_path: Optional[str]
    eda_code: Optional[str]
    feature_engineering_code: Optional[str]
    training_code: Optional[str]
    mlflow_run_id: Optional[str]
    mlflow_model_uri: Optional[str]
    feature_importance: Optional[dict]
    model_file_path: Optional[str]
    best_model_file_path: Optional[str]
    best_feature_importance: Optional[dict]