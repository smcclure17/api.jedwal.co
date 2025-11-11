import json
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, status

from jedwal.account import service as account_service
from jedwal.database.core import DbTable
from jedwal.posts import repository
from jedwal.posts.categories import service as categories_service
from jedwal.posts.google_docs_client import DocAccessException, GoogleDocs
from jedwal.posts.models import Post, PostCreate, PostRead
from jedwal.posts.parsers.doc_ast import (
    GoogleDocsParser,
    Node,
    dict_to_node,
    node_to_dict,
)
from jedwal.posts.parsers.doc_to_md import MarkdownRenderer
from jedwal.posts.parsers.image_handler import ImageHandler

PostImageHandler = Annotated[ImageHandler, Depends(ImageHandler)]


def get_post(*, table: DbTable, owner_id: str, post_id: str) -> Post:
    return repository.get_post(table=table, owner_id=owner_id, post_id=post_id)


def get_post_data(*, table: DbTable, post: Post):
    renderer = MarkdownRenderer()

    if post.frozen:
        raise HTTPException(401, "Post is frozen. Re-upgrade to premium to unfreeze")

    serialized_ast = json.loads(post.google_doc_ast)
    ast: Node = dict_to_node(serialized_ast)

    output = renderer.render(ast)
    return {"content": output, "title": post.title, "document_id": post.google_doc_id}


def get_posts_for_account(*, table: DbTable, owner_id: str) -> list[PostRead]:
    """Get all Posts for an account"""
    posts = repository.get_posts_by_owner(table=table, owner_id=owner_id)

    post_reads = []
    for post in posts:
        # TEMP: load categories into item if they haven't been initialized
        # for denormalized storage yet
        if post.categories is None:
            post.categories = categories_service.get_categories_for_post(
                table=table, owner_id=post.owner_id, post_key=post.post_key
            )

        post_reads.append(
            PostRead(
                post_key=post.post_key,
                owner_id=post.owner_id,
                title=post.title,
                categories=post.categories,
                created_at=post.created_at,
                updated_at=post.updated_at,
                google_doc_id=post.google_doc_id,
            )
        )
    return post_reads


def delete_post(*, table: DbTable, owner_id: str, post_id: str):
    """Delete a Post."""
    repository.delete_post(table=table, owner_id=owner_id, post_key=post_id)


def create_post(
    *, table: DbTable, post_create: PostCreate, image_handler: ImageHandler
) -> Post:
    account = account_service.get_account(table=table, id=post_create.owner_id)
    free_account = account.account_status == "free"

    existing_posts = repository.get_posts_by_owner(
        table=table, owner_id=post_create.owner_id
    )
    if free_account and len(existing_posts) >= 2:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Free accounts can only have 2 posts.",
        ) from None

    google_doc_id = _extract_doc_id_from_url(post_create.google_doc_id)

    existing_post = repository.get_post_by_google_doc_id(
        table=table, owner_id=post_create.owner_id, google_doc_id=google_doc_id
    )
    if existing_post:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"Post already exists for this Google Doc: {existing_post.post_key}",
        ) from None

    google_docs = GoogleDocs.from_token_info(info=post_create.refresh_token_info)

    try:
        google_doc_payload = google_docs.get_document(google_doc_id)
    except DocAccessException as e:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Could not open Document.",
        ) from e

    ast_parser = GoogleDocsParser(google_doc_payload, image_handler=image_handler)
    google_doc_ast_json = node_to_dict(ast_parser.parse())

    post = Post(
        post_key=post_create.post_key,
        owner_id=post_create.owner_id,
        google_doc_id=post_create.google_doc_id,
        google_doc_payload=json.dumps(google_doc_payload),
        google_doc_ast=json.dumps(google_doc_ast_json),
        creator=account.display_name,
        refresh_token_info=post_create.refresh_token_info,
        title=google_doc_payload["title"],
    )

    return repository.create_post(table=table, post=post)


def refresh_post_data(
    *, table: DbTable, owner_id: str, post_id: str, image_handler: PostImageHandler
):
    post = get_post(table=table, owner_id=owner_id, post_id=post_id)
    google_docs = GoogleDocs.from_token_info(info=post.refresh_token_info)
    google_doc_payload = google_docs.get_document(post.google_doc_id)
    parser = GoogleDocsParser(docs_json=google_doc_payload, image_handler=image_handler)

    # TODO: kick off webhooks ...
    # TODO: invalidate cache (CDN)

    return repository.update_post(
        table=table,
        owner_id=post.owner_id,
        post_key=post.post_key,
        updates={
            "google_doc_payload": json.dumps(google_doc_payload),
            "google_doc_ast": json.dumps(node_to_dict(parser.parse())),
            "title": google_doc_payload["title"],
            "updated_at": datetime.now(tz=UTC),
        },
    )


def _extract_doc_id_from_url(google_id_or_url: str) -> str:
    if "docs.google.com/document/d/" in google_id_or_url:
        return google_id_or_url.split("/d/")[1].split("/")[0]
    return google_id_or_url
