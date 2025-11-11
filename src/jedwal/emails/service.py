import logging

from jedwal.common.exceptions import NotFoundException
from jedwal.config.config import settings
from jedwal.database.core import DbTable
from jedwal.emails import ses_client
from jedwal.emails.models import EmailData

logger = logging.getLogger(__name__)


def is_unsubscribed(*, table: DbTable, user_id: str) -> bool:
    from jedwal.account.service import get_account

    try:
        account = get_account(table=table, id=user_id)
        return account.do_not_email
    except Exception:
        return False


def unsubscribe_user(*, table: DbTable, user_id: str) -> bool:
    from jedwal.account.service import get_account, update_account

    account = get_account(table=table, id=user_id)
    if account is None:
        raise NotFoundException("Account not found")

    account = account.model_copy(update={"do_not_email": True})
    update_account(table=table, account=account)


def send_email(*, table: DbTable, email_data: EmailData) -> dict | None:
    if email_data.user_id and is_unsubscribed(table=table, user_id=email_data.user_id):
        logger.info(f"User {email_data.to_email} has unsubscribed, skipping email.")
        return None
    return ses_client.send(email_data=email_data, api_base_url=settings.api_base_url)
