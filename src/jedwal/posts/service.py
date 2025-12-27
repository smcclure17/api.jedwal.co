import json
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends

from jedwal.account import service as account_service
from jedwal.account.models import AccountId
from jedwal.common.encryption.service import Encryption
from jedwal.common.exceptions import ConflictException, UnsupportedMediaTypeException
from jedwal.config import settings
from jedwal.database.core import DbTable, SqSClient
from jedwal.entitlements import service as entitlements_service
from jedwal.posts import repository
from jedwal.posts.google_docs_client import DocAccessException, GoogleDocs
from jedwal.posts.models import Post, PostCreate, PostKey, PostRead
from jedwal.posts.parsers import ast, google_docs_parser, markdown_renderer
from jedwal.posts.parsers.image_handler import ImageHandler


def get_image_handler():
    if settings.enable_internal_image_hosting:
        return ImageHandler()
    return None  # don't re-host images, keep google storage urls


PostImageHandler = Annotated[ImageHandler | None, Depends(get_image_handler)]


def get_post(*, table: DbTable, owner_id: AccountId, post_id: PostKey) -> Post:
    return repository.get_post(table=table, owner_id=owner_id, post_id=post_id)


def get_post_data(*, table: DbTable, post: Post):
    entitlements_service.check_can_access_post(post=post)

    serialized_ast = json.loads(post.google_doc_ast)
    tree = ast.Root.model_validate(serialized_ast)

    if tree.frontmatter is not None:
        frontmatter = tree.frontmatter.model_dump(exclude=["value"])["data"]
    else:
        frontmatter = None

    renderer = markdown_renderer.MarkdownRenderer()
    output = renderer.render(tree)
    return {
        "content": output,
        "title": post.title,
        "document_id": post.google_doc_id,
        "frontmatter": frontmatter,
    }


def get_posts_for_account(*, table: DbTable, owner_id: AccountId) -> list[PostRead]:
    """Get all Posts for an account"""
    posts = repository.get_posts_by_owner(table=table, owner_id=owner_id)
    return [PostRead(**post.model_dump()) for post in posts]


def delete_post(*, table: DbTable, owner_id: AccountId, post_id: PostKey):
    """Delete a Post."""
    repository.delete_post(table=table, owner_id=owner_id, post_key=post_id)


def create_post(
    *,
    table: DbTable,
    encryption: Encryption,
    post_create: PostCreate,
    image_handler: PostImageHandler,
) -> Post:
    account = account_service.get_account(table=table, id=post_create.owner_id)
    existing_posts = repository.get_posts_by_owner(
        table=table, owner_id=post_create.owner_id
    )

    entitlements_service.check_can_create_post(
        account=account, current_count=len(existing_posts)
    )

    google_doc_id = _extract_doc_id_from_url(post_create.google_doc_id)
    existing_post = repository.get_post_by_google_doc_id(
        table=table, owner_id=post_create.owner_id, google_doc_id=google_doc_id
    )
    if existing_post:
        raise ConflictException(
            detail=f"Post already exists for this Google Doc: {existing_post.post_key}",
        ) from None

    google_docs = GoogleDocs.from_token_info(
        info=post_create.refresh_token_info, encryption=encryption
    )

    try:
        google_doc_payload = google_docs.get_document(google_doc_id)
    except DocAccessException as e:
        raise UnsupportedMediaTypeException(detail="Could not open Document.") from e

    parser = google_docs_parser.GoogleDocsParser(image_handler=image_handler)
    google_doc_ast = parser.parse(google_doc_payload)
    google_doc_ast_json = google_doc_ast.model_dump_json()

    post = Post(
        post_key=post_create.post_key,
        owner_id=post_create.owner_id,
        google_doc_id=post_create.google_doc_id,
        google_doc_payload=json.dumps(google_doc_payload),
        google_doc_ast=google_doc_ast_json,
        creator=account.display_name,
        refresh_token_info=post_create.refresh_token_info,
        title=google_doc_payload["title"],
    )

    return repository.create_post(table=table, post=post)


def refresh_post_data(
    *,
    table: DbTable,
    encryption: Encryption,
    queue: SqSClient,
    owner_id: AccountId,
    post_id: PostKey,
    image_handler: PostImageHandler,
):
    from jedwal.posts.webhooks.service import trigger_webhooks_for_post

    post = get_post(table=table, owner_id=owner_id, post_id=post_id)
    google_docs = GoogleDocs.from_token_info(
        info=post.refresh_token_info, encryption=encryption
    )
    google_doc_payload = google_docs.get_document(post.google_doc_id)

    parser = google_docs_parser.GoogleDocsParser(image_handler=image_handler)
    google_doc_ast = parser.parse(google_doc_payload)
    google_doc_ast_json = google_doc_ast.model_dump_json()

    trigger_webhooks_for_post(
        queue=queue, table=table, owner_id=owner_id, post_id=post_id
    )
    # TODO: invalidate cache (CDN)

    return repository.update_post(
        table=table,
        owner_id=post.owner_id,
        post_key=post.post_key,
        updates={
            "google_doc_payload": json.dumps(google_doc_payload),
            "google_doc_ast": google_doc_ast_json,
            "title": google_doc_payload["title"],
            "updated_at": datetime.now(tz=UTC),
        },
    )


def freeze_posts_for_account(*, table: DbTable, owner_id: AccountId, limit=2):
    """Freeze all but the limit oldest posts"""
    posts = get_posts_for_account(table=table, owner_id=owner_id)
    sorted_posts = sorted(posts, key=lambda post: post.created_at)
    posts_to_freeze = sorted_posts[limit:]

    for post in posts_to_freeze:
        if not post.frozen:
            repository.update_post(
                table=table,
                owner_id=owner_id,
                post_key=post.post_key,
                updates={"frozen": True},
            )


def unfreeze_posts_for_account(*, table: DbTable, owner_id: AccountId):
    """Unfreeze all posts"""
    posts = get_posts_for_account(table=table, owner_id=owner_id)

    for post in posts:
        if post.frozen:
            repository.update_post(
                table=table,
                owner_id=owner_id,
                post_key=post.post_key,
                updates={"frozen": False},
            )


def _extract_doc_id_from_url(google_id_or_url: str) -> str:
    if "docs.google.com/document/d/" in google_id_or_url:
        return google_id_or_url.split("/d/")[1].split("/")[0]
    return google_id_or_url
