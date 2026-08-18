import pandas as pd
from evidently import Report
from evidently.presets import DataDriftPreset
from core.logger import get_logger

logger = get_logger(__name__)

def check_drift(reference_df: pd.DataFrame, current_df: pd.DataFrame, drift_threshold: float = 0.5) -> dict:
    try:
        logger.info("Running drift detection")
        
        # Only compare columns that exist in both datasets
        common_columns = list(set(reference_df.columns) & set(current_df.columns))
        reference_df = reference_df[common_columns]
        current_df = current_df[common_columns]
        
        report = Report([DataDriftPreset()])
        evaluation = report.run(current_df, reference_df)
        result = evaluation.dict()
        
        drifted_columns = []
        drifted_share = 0.0
        drifted_count = 0

        for metric in result["metrics"]:
            metric_type = metric["config"]["type"]

            if metric_type == "evidently:metric_v2:DriftedColumnsCount":
                drifted_share = float(metric["value"]["share"])
                drifted_count = int(metric["value"]["count"])
            elif metric_type == "evidently:metric_v2:ValueDrift":
                column = metric["config"]["column"]
                threshold = metric["config"]["threshold"]
                p_value = float(metric["value"])
                if p_value < threshold:
                    drifted_columns.append(column)

        overall_drift = drifted_share >= drift_threshold

        logger.info(f"Drift detected: {overall_drift}, Share: {drifted_share}, Columns: {drifted_columns}")

        return {
            "drift_detected": overall_drift,
            "drift_share": drifted_share,
            "number_of_drifted_columns": drifted_count,
            "drifted_columns": drifted_columns
        }

    except Exception as e:
        logger.error(f"Drift detection failed: {str(e)}")
        return {
            "drift_detected": False,
            "drift_share": 0.0,
            "number_of_drifted_columns": 0,
            "drifted_columns": [],
            "error": str(e)
        }
