# backend/agents/nodes.py
from agents.llm import get_llm
from langchain_core.messages import HumanMessage
from agents.state import AgentState
from agents.sandbox import execute_code
from core.logger import get_logger
from models.schemas import CriticReview
import os
import json
import shutil
import re
from langgraph.graph import StateGraph, START, END
import mlflow
from core.config import MLFLOW_TRACKING_URI

logger = get_logger(__name__)

llm = get_llm()

MAX_RETRIES = 3
#Helper 
def clean_code(code: str) -> str:
    """Remove markdown code blocks if LLM wraps code in them"""
    if code.startswith("```"):
        # Remove first line (```python or ```)
        code = code.split("\n", 1)[1] if "\n" in code else ""
    if code.endswith("```"):
        # Remove last line
        code = code.rsplit("\n", 1)[0] if "\n" in code else code
    return code.strip()

#Helper 
def truncate_error(error: str, max_lines: int = 10) -> str:
    lines = str(error).split('\n')
    if len(lines) > max_lines:
        return '\n'.join(lines[-max_lines:])
    return error

def parse_json_with_numpy_scalars(raw: str) -> dict:
    cleaned = re.sub(r"np\.float\d*\(([^()]+)\)", r"\1", raw)
    cleaned = re.sub(r"np\.int\d*\(([^()]+)\)", r"\1", cleaned)
    return json.loads(cleaned)

def build_default_training_code(column_mapping: dict) -> str:
    price_column = column_mapping.get("pricing_column")
    demand_column = column_mapping.get("demand_column")
    date_column = column_mapping.get("date_column")
    return f"""
import json
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor, GradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

df = pd.read_csv('/data/engineered.csv')

date_column = {json.dumps(date_column)}
demand_column = {json.dumps(demand_column)}
price_column = {json.dumps(price_column)}

if date_column and date_column in df.columns:
    df[date_column] = pd.to_datetime(df[date_column], errors='coerce')
    df = df.sort_values(date_column)

y = df[demand_column]
X = df.drop(columns=[demand_column, date_column], errors='ignore')
X = X.select_dtypes(include='number')

if price_column not in X.columns:
    raise ValueError(f"Price column {{price_column}} is missing from numeric model features")

split_index = int(len(df) * (0.7 if len(df) < 100 else 0.8))
split_index = min(max(split_index, 1), len(df) - 1)

X_train, X_test = X.iloc[:split_index], X.iloc[split_index:]
y_train, y_test = y.iloc[:split_index], y.iloc[split_index:]

models = [
    RandomForestRegressor(n_estimators=200, random_state=42),
    GradientBoostingRegressor(random_state=42),
    ExtraTreesRegressor(n_estimators=200, random_state=42),
]

best_model = None
best_metrics = None
best_rmse = float('inf')

for model in models:
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
    metrics = {{
        "rmse": rmse,
        "mae": float(mean_absolute_error(y_test, y_pred)),
        "r2": float(r2_score(y_test, y_pred)),
    }}
    if rmse < best_rmse:
        best_rmse = rmse
        best_model = model
        best_metrics = metrics

feature_importance = {{
    feature: float(value)
    for feature, value in zip(X.columns, best_model.feature_importances_)
}}

print("METRICS: " + json.dumps(best_metrics))
print("FEATURE_IMPORTANCE: " + json.dumps(feature_importance))
joblib.dump(best_model, '/data/model.pkl')
""".strip()

def load_data(state: AgentState) -> dict:
    file_path = state["file_path"]
    logger.info(f"Loading data from {file_path}")
    
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return {"error": f"File not found: {file_path}", "status": "failed"}
    
    logger.info("File found, proceeding to EDA")
    return {"status": "eda", "error": None}

def eda(state: AgentState) -> dict:
    logger.info("Starting EDA")
    
    column_mapping = state["column_mapping"]
    file_path = state["file_path"]
    previous_eda_code = state.get("eda_code")
    eda_feedback = state.get("eda_feedback")

    previous_code_prompt = ""
    if previous_eda_code and eda_feedback:
        previous_code_prompt = f"""
        Here is your previous EDA code:
        {previous_eda_code}
        
        The critic gave this feedback on your EDA:
        {eda_feedback}
        
        Improve upon this code addressing the feedback.
        """
    
    prompt = f"""
    You are a senior data scientist. You have a CSV file at /data/input.csv with the following column mapping:
    {column_mapping}
    
    {previous_code_prompt}
    
    Write Python code to perform thorough exploratory data analysis on this dataset. Your code should:
    1. Load the CSV file
    2. Print shape, dtypes, and null counts
    3. Print basic statistics (describe())
    4. Print value counts for categorical columns
    5. Check for outliers in numeric columns
    6. Print correlation between numeric columns
    
    Return ONLY the Python code, no explanation, no markdown, no backticks.
    Just raw executable Python code.
    """
    
    response = llm.invoke([HumanMessage(content=prompt)])
    code = clean_code(response.content.strip())
    logger.info("EDA code generated")
    
    result = execute_code(code, files = {"/data/input.csv": file_path})
    logger.info("EDA code executed")
    
    return {
        "eda_code": code,
        "execution_result": result,
        "status": "feature_engineering"
    }

def feature_engineering(state: AgentState) -> dict:
    logger.info("Starting feature engineering")
    
    column_mapping = state["column_mapping"]
    eda_results = state["execution_result"]
    file_path = state["file_path"]
    unique_id = state["unique_id"]
    previous_fe_code = state.get("feature_engineering_code")
    fe_feedback = state.get("feature_engineering_feedback")

    previous_code_prompt = ""
    if previous_fe_code and fe_feedback:
        previous_code_prompt = f"""
        The critic gave this feedback on your previous feature engineering:
        {fe_feedback}
        Address this feedback in your new code.
        """

    base_prompt = f"""
    You are a data scientist. You have a CSV file at /data/input.csv with the following column mapping:
    {column_mapping}
    
    Here are the results from the EDA:
    {eda_results}
    
    {previous_code_prompt}
    
    Write Python code to engineer features for a demand forecasting and price optimization model.
    Your code should:
    1. Load the CSV file
    2. Handle missing values — ONLY fill numeric columns with their mean:
       numeric_cols = df.select_dtypes(include='number').columns
       df[numeric_cols] = df[numeric_cols].fillna(df[numeric_cols].mean())
    3. Parse date column if it exists — convert to datetime, extract day_of_week, month, day
    4. Encode categorical columns using label encoding
    5. Keep the original date column in the output, but exclude it when defining feature columns for any modeling step downstream
    6. Print the final dataframe shape and columns
    7. Save the engineered dataframe to /data/engineered.csv
    
    IMPORTANT:
    - Never call df.mean() or df.fillna() on the entire dataframe
    - Always save to /data/engineered.csv before the script ends
    - Use only pandas, numpy, sklearn — they are already installed
    
    Return ONLY raw Python code. No markdown, no backticks, no explanation.
    """

    MAX_RETRIES = 3
    prompt = base_prompt
    code = None
    result = None

    for attempt in range(MAX_RETRIES):
        logger.info(f"Feature engineering attempt {attempt + 1}")
        response = llm.invoke([HumanMessage(content=prompt)])
        code = clean_code(response.content.strip())
        
        result = execute_code(
            code,
            files={"/data/input.csv": file_path},
            output_files=["/data/engineered.csv"]
        )

        if result["stderr"]:
            logger.error(f"Feature engineering stderr: {result['stderr']}")
        if result["stdout"]:
            logger.info(f"Feature engineering stdout: {result['stdout']}")

        error_detail = None
        if result["error"]:
            error_detail = truncate_error(str(result["error"]))
        elif not result["output_files"].get("/data/engineered.csv"):
            error_detail = "/data/engineered.csv was not saved by the code"

        if error_detail:
            logger.error(f"Attempt {attempt + 1} failed: {error_detail}")
            prompt = base_prompt + f"""

Your previous attempt (attempt {attempt + 1}) wrote this code:
{code}

It failed with this error:
{error_detail}

Fix the code addressing this specific error and try again.
Return ONLY raw Python code. No markdown, no backticks, no explanation.
"""
            continue

        logger.info(f"Feature engineering succeeded on attempt {attempt + 1}")
        break

    engineered_file_path = None
    if result and result["output_files"].get("/data/engineered.csv"):
        engineered_file_path = f"data/processed/{unique_id}_engineered.csv"
        os.makedirs("data/processed", exist_ok=True)
        content = result["output_files"]["/data/engineered.csv"]
        if isinstance(content, str):
            content = content.encode()
        with open(engineered_file_path, "wb") as f:
            f.write(content)
        logger.info(f"Engineered file saved locally: {engineered_file_path}")
    else:
        logger.error("Feature engineering failed after all retries")

    return {
        "feature_engineering_code": code,
        "execution_result": result,
        "engineered_file_path": engineered_file_path,
        "status": "train_model"
    }


def train_model(state: AgentState) -> dict:
    logger.info("Starting model training")
    
    column_mapping = state["column_mapping"]
    engineered_file_path = state["engineered_file_path"]
    unique_id = state["unique_id"]
    previous_metrics = state.get("previous_metrics")
    iteration_count = state.get("iteration_count", 0)
    previous_training_code = state.get("training_code")
    critic_feedback = state.get("model_training_feedback")

    if not engineered_file_path:
        logger.error("No engineered file path — feature engineering must have failed")
        return {
            "status": "failed",
            "error": "Feature engineering failed, no engineered dataset available"
        }

    previous_metrics_prompt = ""
    if previous_metrics:
        previous_metrics_prompt = f"""
        The previous model achieved these metrics:
        {previous_metrics}
        Try to beat these metrics.
        """

    previous_code_prompt = ""
    if previous_training_code and critic_feedback:
        previous_code_prompt = f"""
        The critic gave this feedback on your previous training:
        {critic_feedback}
        Address this feedback in your new code.
        """

    base_prompt = f"""
    You are a data scientist. You have an engineered CSV file at /data/engineered.csv with the following column mapping:
    {column_mapping}
    
    This is iteration {iteration_count + 1} of model training.
    Your previous iteration's code was: 
    {previous_training_code}
    {previous_metrics_prompt}
    {previous_code_prompt}
    
    Write Python code to train a demand forecasting model. Your code should:
    1. Load the engineered CSV file from /data/engineered.csv
    2. Use the price column as a key feature
    3. If the date column (from column_mapping: {column_mapping.get("date_column")}) exists in the dataframe,
       sort the dataframe by this date column in ascending order before splitting.
       This is time-series data — do NOT use random shuffling for train/test split.
    First check the size of the dataset with len(df):
   - If less than 50 rows, use TimeSeriesSplit cross-validation
   - If less than 100 rows, use a 70/30 chronological split (earliest 70% as train, latest 30% as test)
   - Otherwise use an 80/20 chronological split (earliest 80% as train, latest 20% as test)
   After splitting, drop the date column itself — do NOT use it as a model feature.
    4. Train a model to predict the demand column
    5. Evaluate the model and print metrics in this EXACT format on a single line:
       METRICS: {{"rmse": 1.23, "mae": 0.45, "r2": 0.89}}
    6. Extract feature importances and print in this EXACT format on a single line:
       FEATURE_IMPORTANCE: {{"feature_name": 0.123, "other_feature": 0.456}}
    7. Save the trained model to /data/model.pkl using joblib
    
    IMPORTANT:
    - Use only numeric columns as features
    - Drop any remaining string or datetime columns before training
    - Never fail if the date column is already missing; use drop(columns=[...], errors='ignore')
    - Use scikit-learn models only
    - Always save the model to /data/model.pkl before the script ends
    - joblib and sklearn are already installed
    - Print METRICS and FEATURE_IMPORTANCE as valid JSON with double quotes only
    - Do NOT use np.float64() or any numpy types in the output — convert to plain Python floats using float()
    - Each print statement must be on its own single line
    - Models that support feature_importances_: RandomForestRegressor, GradientBoostingRegressor, ExtraTreesRegressor, XGBRegressor
    - Models that do NOT support feature_importances_: SVR, LinearRegression, Ridge, Lasso, KNeighborsRegressor
    - You MUST train at least one model from the first list to extract feature importances
    - You can train additional models from either list to compare performance
    - Pick the best performing model based on RMSE as your final model to save
    - Extract feature importances ONLY from a model in the first list
    - Save ONLY the best performing model to /data/model.pkl
    - Print only ONE METRICS line for the best model
    - Print only ONE FEATURE_IMPORTANCE line from a model that supports it
    - Do NOT use GridSearchCV on small datasets — it causes issues with less than 10 samples per fold
        
    Return ONLY raw Python code. No markdown, no backticks, no explanation.
    """

    prompt = base_prompt
    code = None
    result = None
    metrics = {}
    feature_importance = {}

    for attempt in range(MAX_RETRIES):
        logger.info(f"Training attempt {attempt + 1}")
        response = llm.invoke([HumanMessage(content=prompt)])
        code = clean_code(response.content.strip())

        result = execute_code(
            code,
            files={"/data/engineered.csv": engineered_file_path},
            output_files=["/data/model.pkl"]
        )

        if result["stderr"]:
            logger.error(f"Training stderr: {result['stderr']}")
        if result["stdout"]:
            logger.info(f"Training stdout: {result['stdout']}")
        if result["error"]:
            logger.error(f"Training error: {result['error']}")

        # Check for sandbox execution error first
        error_detail = None
        if result["error"]:
            error_detail = truncate_error(str(result["error"]))
        elif not result["output_files"].get("/data/model.pkl"):
            error_detail = "/data/model.pkl was not saved by the code"

        if error_detail:
            logger.error(f"Training attempt {attempt + 1} failed: {error_detail}")
            prompt = base_prompt + f"""
                        Your previous attempt wrote this code:
                        {code}

                        It failed with this exact error:
                        {error_detail}

                        Fix the issue based on the actual error message above.
                        Return ONLY raw Python code. No markdown, no backticks, no explanation.
                    """
            continue

        # Parse metrics and feature importance
        full_output = "\n".join(result["stdout"]) if result["stdout"] else ""
        error_detail = None

        if "METRICS:" in full_output:
            try:
                metrics_line = [l for l in full_output.split("\n") if "METRICS:" in l][0]
                metrics_str = metrics_line.split("METRICS:")[1].strip()
                metrics = json.loads(metrics_str)
                logger.info(f"Parsed metrics: {metrics}")
            except Exception as e:
                error_detail = f"Metrics were printed but failed to parse. Exact error: {str(e)}. Raw output was: {full_output}"
                logger.error(error_detail)
        else:
            error_detail = f"No METRICS found in output. Full output was: {full_output}"

        if "FEATURE_IMPORTANCE:" in full_output:
            try:
                fi_line = [l for l in full_output.split("\n") if "FEATURE_IMPORTANCE:" in l][0]
                fi_str = fi_line.split("FEATURE_IMPORTANCE:")[1].strip()
                feature_importance = parse_json_with_numpy_scalars(fi_str)
                logger.info(f"Parsed feature importance: {feature_importance}")
            except Exception as e:
                logger.error(f"Feature importance parse error: {str(e)}. Raw: {fi_str}")

        if metrics:
            logger.info(f"Training succeeded on attempt {attempt + 1}")
            break
        else:
            logger.error(f"Training attempt {attempt + 1} failed: {error_detail}")
            prompt = base_prompt + f"""
                            Your previous attempt wrote this code:
                            {code}

                            It produced this output:
                            {full_output}

                            It failed with this exact error:
                            {error_detail}

                            Fix the issue based on the actual error message above.
                            Return ONLY raw Python code. No markdown, no backticks, no explanation.
                            """

    if not metrics:
        logger.info("LLM training attempts failed, running default training fallback")
        code = build_default_training_code(column_mapping)
        result = execute_code(
            code,
            files={"/data/engineered.csv": engineered_file_path},
            output_files=["/data/model.pkl"]
        )

        if result["stderr"]:
            logger.error(f"Fallback training stderr: {result['stderr']}")
        if result["stdout"]:
            logger.info(f"Fallback training stdout: {result['stdout']}")
        if result["error"]:
            logger.error(f"Fallback training error: {result['error']}")

        full_output = "\n".join(result["stdout"]) if result["stdout"] else ""
        if not result["error"] and "METRICS:" in full_output:
            try:
                metrics_line = [l for l in full_output.split("\n") if "METRICS:" in l][0]
                metrics = json.loads(metrics_line.split("METRICS:")[1].strip())
                logger.info(f"Parsed fallback metrics: {metrics}")
            except Exception as e:
                logger.error(f"Fallback metrics parse error: {str(e)}. Raw output was: {full_output}")

        if not result["error"] and "FEATURE_IMPORTANCE:" in full_output:
            try:
                fi_line = [l for l in full_output.split("\n") if "FEATURE_IMPORTANCE:" in l][0]
                feature_importance = parse_json_with_numpy_scalars(
                    fi_line.split("FEATURE_IMPORTANCE:")[1].strip()
                )
                logger.info(f"Parsed fallback feature importance: {feature_importance}")
            except Exception as e:
                logger.error(f"Fallback feature importance parse error: {str(e)}. Raw output was: {full_output}")

    model_file_path = None
    if result and result["output_files"].get("/data/model.pkl") is not None:
        model_file_path = f"data/models/{unique_id}_iter{iteration_count + 1}_model.pkl"
        os.makedirs("data/models", exist_ok=True)
        content = result["output_files"]["/data/model.pkl"]
        if isinstance(content, str):
            content = content.encode()
        with open(model_file_path, "wb") as f:
            f.write(content)
        logger.info(f"Model saved locally: {model_file_path}")

    logger.info(f"model_file_path before return: {model_file_path}")
    logger.info(f"result output_files keys: {list(result['output_files'].keys()) if result else 'no result'}")
    logger.info(f"model pkl value is not None: {result['output_files'].get('/data/model.pkl') is not None}")
    return {
        "training_code": code,
        "execution_result": result,
        "model_metrics": metrics,
        "feature_importance": feature_importance,
        "model_file_path": model_file_path,
        "iteration_count": iteration_count + 1,
        "status": "evaluate"
    }

def evaluate(state: AgentState) -> dict:
    logger.info("Evaluating model metrics")
    logger.info(f"State keys at evaluation: best_model_file_path={state.get('best_model_file_path')}, model_file_path={state.get('model_file_path')}")
    current_metrics = state.get("model_metrics", {})
    best_metrics = state.get("best_metrics")
    iteration_count = state.get("iteration_count", 0)
    
    MAX_ITERATIONS = 5
    IMPROVEMENT_THRESHOLD = 0.01
    
    if not current_metrics.get("rmse"):
        logger.error("No metrics found, stopping")
        return {"status": "failed", "error": "No metrics produced by training"}
    
    if not best_metrics:
        logger.info(f"First iteration, setting as best metrics: {current_metrics}")
        return {
            "best_metrics": current_metrics,
            "best_model_file_path": state.get("model_file_path"),
            "best_feature_importance": state.get("feature_importance"),
            "status": "train_model" if iteration_count < MAX_ITERATIONS else "critic_review"
        }
    
    previous_rmse = best_metrics.get("rmse")
    current_rmse = current_metrics.get("rmse")
    improvement = (previous_rmse - current_rmse) / previous_rmse
    
    logger.info(f"Improvement: {improvement:.2%} | Iteration: {iteration_count}/{MAX_ITERATIONS}")
    
    if improvement > IMPROVEMENT_THRESHOLD:
        if iteration_count < MAX_ITERATIONS:
            logger.info("Meaningful improvement found, continuing training")
            return {
                "best_metrics": current_metrics,
                "best_model_file_path": state.get("model_file_path"),
                "best_feature_importance": state.get("feature_importance"),
                "status": "train_model"
            }
        else:
            logger.info("Improvement found but iteration limit reached, moving to critic")
            return {
                "best_metrics": current_metrics,
                "best_model_file_path": state.get("model_file_path"),
                "best_feature_importance": state.get("feature_importance"),
                "status": "critic_review"
            }
    else:
        logger.info("No improvement, keeping current best model")
        return {"status": "critic_review"}
    
def critic_review(state: AgentState) -> dict:
    logger.info("Starting critic review")
    logger.info(f"State keys at critic_review: best_model_file_path={state.get('best_model_file_path')}, model_file_path={state.get('model_file_path')}")
    structured_llm = llm.with_structured_output(CriticReview)
    prompt = f"""
    You are a senior data scientist reviewing the work of a junior data scientist who has trained a demand 
    forecasting model. The junior data scientist has completed {state.get("iteration_count", 0)} iterations of training.
    
    EDA Code:
    {state.get("eda_code")}
    
    Feature Engineering Code:
    {state.get("feature_engineering_code")}
    
    Training Code:
    {state.get("training_code")}
    
    Best metrics achieved:
    {state.get("best_metrics")}
    
    Review each stage separately and provide targeted feedback:
    - eda_feedback: issues with the exploratory analysis
    - feature_engineering_feedback: issues with feature creation or data preparation
    - model_training_feedback: issues with model selection, training, or evaluation
    
    If you reject, specify restart_from as one of: "eda", "feature_engineering", "train_model"
    Choose the earliest stage that needs fixing.
    APPROVAL CRITERIA:
    - If R2 score is above 0.80, you MUST approve unless there is a critical data leakage issue
    - Do not reject for minor improvements or stylistic preferences
    - Only reject if there is a fundamental flaw — data leakage, wrong target variable, or metrics are suspicious
    - Keep all feedback fields to 2-3 sentences maximum
    """

    review = structured_llm.invoke([HumanMessage(content=prompt)])
    logger.info(f"Critic review completed. Approved: {review.approved}")
    logger.info(f"Critic feedback — EDA: {review.eda_feedback}")
    logger.info(f"Critic feedback — FE: {review.feature_engineering_feedback}")
    logger.info(f"Critic feedback — Training: {review.model_training_feedback}")

    return {
        "eda_feedback": review.eda_feedback,
        "feature_engineering_feedback": review.feature_engineering_feedback,
        "model_training_feedback": review.model_training_feedback,
        "critic_approved": review.approved,
        "iteration_count": 0,
        "status": "register_model" if review.approved else review.restart_from or "train_model"
    }

def register_model(state: AgentState) -> dict:
    logger.info("Registering model in MLflow")
    logger.info(f"State keys at registration: best_model_file_path={state.get('best_model_file_path')}, model_file_path={state.get('model_file_path')}")
    
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment("dynamic-pricing")
    
    #model_file_path = state.get("model_file_path")
    model_file_path = state.get("best_model_file_path") or state.get("model_file_path")
    best_metrics = state.get("best_metrics")
    unique_id = state.get("unique_id")
    column_mapping = state.get("column_mapping")
    
    if not model_file_path:
        logger.error("No model file found to register")
        return {"status": "failed", "error": "No model file found"}
    
    with mlflow.start_run(run_name=f"pricing-model-{unique_id}") as run:
        # Log metrics
        if best_metrics:
            mlflow.log_metrics(best_metrics)
        
        # Log column mapping as params
        if column_mapping:
            mlflow.log_params({
                "price_column": column_mapping.get("pricing_column"),
                "demand_column": column_mapping.get("demand_column"),
                "date_column": column_mapping.get("date_column"),
            })

        feature_importance = state.get("best_feature_importance") or state.get("feature_importance")
        if feature_importance:
            mlflow.log_dict(feature_importance, "feature_importance.json")
        
        # The model is trained inside the sandbox, whose sklearn internals can differ
        # from the backend environment. Keep the pickle as an artifact and load it
        # only inside the sandbox when computing predictions.
        os.makedirs("data/temp", exist_ok=True)
        temp_model_path = "data/temp/model.pkl"
        shutil.copyfile(model_file_path, temp_model_path)
        mlflow.log_artifact(temp_model_path, artifact_path="model")
        # Log codes as artifacts for reproducibility
        eda_code = state.get("eda_code")
        fe_code = state.get("feature_engineering_code")
        training_code = state.get("training_code")
        
        for filename, code in [("eda.py", eda_code), ("feature_engineering.py", fe_code), ("training.py", training_code)]:
            if code:
                temp_path = f"data/temp/{filename}"
                with open(temp_path, "w") as f:
                    f.write(code)
                mlflow.log_artifact(temp_path, artifact_path="code")
        
        run_id = run.info.run_id
        model_uri = f"runs:/{run_id}/model/model.pkl"
        
        logger.info(f"Model artifact logged in MLflow. Run ID: {run_id}")
    
    return {
        "status": "completed",
        "mlflow_run_id": run_id,
        "mlflow_model_uri": model_uri,
        "best_model_file_path": model_file_path
    }

