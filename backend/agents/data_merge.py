import pandas as pd
import os
from core.logger import get_logger

logger = get_logger(__name__)

def merge_with_reference(
    new_file_path: str,
    reference_path: str,
    user_id: int
) -> dict:
    """
    Merges new upload with existing reference dataset, deduplicates,
    and saves the result as the new reference dataset.
    
    Returns dict with: merged_file_path, new_data_df (for drift comparison), is_first_upload
    """
    new_df = pd.read_csv(new_file_path)
    
    os.makedirs("data/reference", exist_ok=True)
    merged_path = f"data/reference/{user_id}.csv"
    
    if not reference_path or not os.path.exists(reference_path):
        logger.info(f"No existing reference data for user {user_id}, treating as first upload")
        new_df.to_csv(merged_path, index=False)
        return {
            "merged_file_path": merged_path,
            "new_data_df": new_df,
            "old_reference_df": None,
            "is_first_upload": True
        }
    
    old_reference_df = pd.read_csv(reference_path)
    logger.info(f"Merging new upload ({len(new_df)} rows) with reference ({len(old_reference_df)} rows)")
    
    combined_df = pd.concat([old_reference_df, new_df], ignore_index=True)

    combined_df = combined_df.drop_duplicates(keep="last")
    
    combined_df.to_csv(merged_path, index=False)
    logger.info(f"Merged dataset saved: {len(combined_df)} rows after dedup")
    
    return {
        "merged_file_path": merged_path,
        "new_data_df": new_df,
        "old_reference_df": old_reference_df,
        "is_first_upload": False
    }