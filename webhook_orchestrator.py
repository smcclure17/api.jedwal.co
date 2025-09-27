"""Lambda handler to process webhook calls from SQS queue"""

import json
import logging
import os
import requests

from sheetsapi import config, sentry_helpers
from sheetsapi.webhook_repo import WebhookRepo

config.Config.init()

if os.getenv("LAMBDA_TASK_ROOT"):
    sentry_helpers.init()

logger = logging.getLogger(__name__)

repo = WebhookRepo.from_table_name()


def call_webhook(url: str, method: str = "POST", payload: dict | None = None) -> bool:
    """Make the webhook HTTP call and return True if <400 response"""
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "SheetsAPI-Webhook/1.0",
    }

    try:
        if method.upper() == "GET":
            resp = requests.get(url, headers=headers, timeout=10)
        else:
            resp = requests.post(url, json=payload or {}, headers=headers, timeout=10)

        logger.info("Webhook %s %s -> %s", method, url, resp.status_code)
        return resp.status_code < 400

    except requests.Timeout:
        logger.error("Webhook timeout: %s", url)
    except Exception:
        logger.exception("Webhook error: %s", url)

    return False


def process_message(message: dict) -> bool:
    """Process a single webhook message"""
    url = message.get("webhookUrl")
    if not url:
        logger.error("Missing webhookUrl in message")
        return False

    method = message.get("method", "POST")
    payload = message.get("payload", {})
    attempt = message.get("retryCount", 0) + 1

    logger.info("Processing webhook %s (attempt %d)", url, attempt)
    return call_webhook(url, method, payload)


def handler(event, _context):
    """Lambda entrypoint: process webhook calls from SQS queue"""
    failed_ids = []

    for record in event.get("Records", []):
        try:
            body = json.loads(record["body"])
            if not process_message(body):
                failed_ids.append(record["messageId"])
        except Exception:
            logger.exception("Error processing record %s", record.get("messageId"))
            failed_ids.append(record["messageId"])

    if failed_ids:
        logger.warning("Failed to process %d webhook messages", len(failed_ids))
        return {"batchItemFailures": [{"itemIdentifier": i} for i in failed_ids]}

    logger.info("All %d webhook messages processed successfully", len(event.get("Records", [])))
    return {"statusCode": 200}
