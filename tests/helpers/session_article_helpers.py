"""Explicit current-baseline setup for existing single-writer article scenarios."""
from player_wiki.session_models import session_article_base_token


def article_base_token(client, article_id=1):
    with client.application.app_context():
        store = client.application.extensions["campaign_session_service"].store
        article = store.get_article(article_id)
        return session_article_base_token(article, store.get_article_image(article_id)) if article else "v1:" + "0" * 64
