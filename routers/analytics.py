"""
Analytics endpoints for API usage.
"""
import logging
import re
from fastapi import APIRouter, HTTPException

from sheetsapi import analytics_client
from sheetsapi.models.api_models import ApiInvocationResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["analytics"])
analytics_handler = analytics_client.AnalyticsClient()


@router.get("/get-api-invocations")
def get_sheet_invocations(sheet_api_id: str, start_time: str):
    """
    Get API invocation logs for a specific sheet.
    
    Args:
        api_name: Name of the API
        start_time: ISO-8601 formatted start time for log retrieval
        
    Returns:
        List of invocation logs
    """
    date_regex = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    if not re.match(date_regex, start_time):
        raise HTTPException(
            status_code=400, detail="Invalid start time format. Use ISO 8601 format."
        )
    logs = analytics_handler.get_api_logs(sheet_api_id, start_time)
    return [ApiInvocationResponse.from_db_dict(log) for log in logs]


@router.get("/get-api-invocations-total")
def get_sheet_invocations_total(sheet_api_id: str):
    """
    Get the total count of API invocations for a specific sheet.
    
    Args:
        sheet_api_id: ID of the API
        
    Returns:
        Total count of invocations
    """
    return analytics_handler.get_api_total_invocations(sheet_api_id)