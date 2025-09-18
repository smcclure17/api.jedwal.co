from datetime import datetime
import json
import logging
import boto3
from botocore.exceptions import ClientError
from sheetsapi import config

logger = logging.getLogger(__name__)

WEBHOOK_QUEUE_URL = config.Config.Constants.WEBHOOK_QUEUE_URL

def create_webhook_event(
    webhook_url: str,
    method: str,
    payload: dict,
    user_id: str,
    api_name: str,
    retry_count: int = 0
) -> bool:
    """
    Send a webhook event to the SQS queue for processing.
    
    Args:
        webhook_url: The webhook URL to call
        method: HTTP method (GET or POST)
        payload: JSON payload to send
        user_id: User ID for tracking
        api_name: API name for tracking
        retry_count: Current retry count (0 for first attempt)
    
    Returns:
        bool: True if successfully queued, False otherwise
    """
    try:
        sqs = boto3.client('sqs')
        
        message_body = {
            "webhookUrl": webhook_url,
            "method": method,
            "payload": payload,
            "userId": user_id,
            "apiName": api_name,
            "retryCount": retry_count,
            "timestamp": datetime.now().isoformat()
        }
        print("BODYY", message_body)

        response = sqs.send_message(
            QueueUrl=WEBHOOK_QUEUE_URL,
            MessageBody=json.dumps(message_body)
        )
        
        logger.info(f"Webhook event queued successfully: {webhook_url} (MessageId: {response['MessageId']})")
        return True
        
    except ClientError as e:
        logger.error(f"Failed to queue webhook event: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error queuing webhook event: {str(e)}")
        return False


def trigger_webhooks_for_doc(owner_id: str, api_name: str, event_data: dict = None) -> int:
    """
    Trigger all webhooks for a specific document API.
    
    Args:
        owner_id: Owner of the document
        api_name: Name of the API
        event_data: Optional event data to include in webhook payload
    
    Returns:
        int: Number of webhooks successfully queued
    """
    try:
        # Get the document API and its webhooks
        from sheetsapi.doc_repo import DocApiRepo
        doc_repo = DocApiRepo.from_table_name()
        
        api_metadata = doc_repo.get_api_metadata(owner_id, api_name)
        webhooks = api_metadata.webhooks or []
        
        if not webhooks:
            logger.warning(f"No webhooks configured for {owner_id}/{api_name}")
            return 0
        
        # Default event payload
        default_payload = {
            "event": "doc.republished",
            "owner_id": owner_id,
            "api_name": api_name,
            "timestamp": datetime.now().isoformat(),
            **(event_data or {})
        }
        
        successful_queues = 0
        
        for webhook in webhooks:
            # Use webhook's payload if it exists, otherwise use default
            payload = webhook.payload if webhook.payload else default_payload
            
            success = create_webhook_event(
                webhook_url=webhook.url,
                method=webhook.method,
                payload=payload,
                user_id=owner_id,
                api_name=api_name
            )
            
            if success:
                successful_queues += 1
        
        logger.info(f"Queued {successful_queues}/{len(webhooks)} webhooks for {owner_id}/{api_name}")
        return successful_queues
        
    except Exception as e:
        logger.error(f"Failed to trigger webhooks for {owner_id}/{api_name}: {str(e)}")
        return 0