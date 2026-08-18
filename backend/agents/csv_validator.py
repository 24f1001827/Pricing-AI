from agents.llm import get_validation_llm
from langchain_core.messages import HumanMessage
import pandas as pd
from models.schemas import CSVValidationResult

llm = get_validation_llm()
structured_llm = llm.with_structured_output(CSVValidationResult)

def validate_and_map_columns(df: pd.DataFrame) -> CSVValidationResult:
    columns = df.columns.tolist()
    sample_rows = df.head(5).to_string()
    
    prompt = f"""
    You are a data analyst reviewing a CSV dataset to determine if it is relevant 
    for a dynamic pricing and demand forecasting system.
    
    The dataset has the following columns:
    {columns}
    
    Here are a few sample rows:
    {sample_rows}
    
    Determine:
    1. Is this dataset relevant for pricing and demand analysis? 
       It should contain sales volumes, prices, or related business metrics.
       If it contains completely unrelated data (weather only, medical records, 
       social media data etc.), mark it as not relevant.
    
    2. If relevant, identify:
       - Which column represents price
       - Which column represents demand or units sold
       - Which column represents date or time (if any)
       - Any other useful columns for demand forecasting
    A date or time column is required. If no date column exists, mark the dataset as not relevant and explain why.
    
    Be flexible with column names. For example, "price" could be named "cost", "amount", "sale_price" etc.
    """
    
    result = structured_llm.invoke([HumanMessage(content=prompt)])
    return result