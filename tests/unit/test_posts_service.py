from datetime import UTC, datetime, timedelta
from jedwal.posts import service


def test_freeze_posts_for_account(dynamodb_table, sample_post):
    from jedwal.posts import repository

    account_id = sample_post.owner_id
    limit = 2

    # setup/create sample posts
    for i, char in enumerate(["a", "b", "c", "d"]):
        new_post = sample_post.model_copy(
            update={
                "post_key": sample_post.post_key + char,
                "google_doc_id": sample_post.google_doc_id + char,
                "created_at": datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=i),
            }
        )
        repository.create_post(table=dynamodb_table, post=new_post)
    service.freeze_posts_for_account(
        table=dynamodb_table, owner_id=account_id, limit=limit
    )

    # now check they froze the correct ones
    posts = repository.get_posts_by_owner(table=dynamodb_table, owner_id=account_id)
    sorted_posts = sorted(posts, key=lambda post: post.created_at, reverse=True)

    frozen = sorted_posts[:limit]
    unfrozen = sorted_posts[limit:]
    assert all(post.frozen for post in frozen)
    assert all(not post.frozen for post in unfrozen)


def test_unfreeze_posts_for_account(dynamodb_table, sample_post):
    from jedwal.posts import repository

    account_id = sample_post.owner_id

    # setup/create sample posts. Some frozen, some not
    for i, post in enumerate([("a", True), ("b", True), ("c", True), ("d", False)]):
        char, frozen = post
        new_post = sample_post.model_copy(
            update={
                "post_key": sample_post.post_key + char,
                "google_doc_id": sample_post.google_doc_id + char,
                "created_at": datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=i),
                "frozen": frozen,
            }
        )
        repository.create_post(table=dynamodb_table, post=new_post)
    service.unfreeze_posts_for_account(table=dynamodb_table, owner_id=account_id)

    # make sure all are unfrozen
    posts = repository.get_posts_by_owner(table=dynamodb_table, owner_id=account_id)
    assert all(not post.frozen for post in posts)
