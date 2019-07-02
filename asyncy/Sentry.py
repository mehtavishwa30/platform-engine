# -*- coding: utf-8 -*-
from raven import Client

from .Exceptions import StoryscriptError
from .Stories import Stories


class Sentry:
    _sentry_client = None

    @classmethod
    def init(cls, dsn: str, release: str):
        """
        Initialises Sentry without breadcrumbs, logging hook, and
        hook libraries as Sentry relies on a thread local for it's context,
        which is not feasible in an asyncio context.
        """
        if dsn is None:
            return

        cls._sentry_client = Client(
            dsn=dsn,
            enable_breadcrumbs=False,
            install_logging_hook=False,
            hook_libraries=[],
            release=release)

    @classmethod
    def capture_exc(cls, exc_info: BaseException,
                    story: Stories = None, line: dict = None,
                    extra: dict = None):
        if cls._sentry_client is None:
            return

        cls._sentry_client.context.clear()

        if isinstance(exc_info, StoryscriptError):
            story = exc_info.story
            line = exc_info.line

        app_uuid = None
        version = None
        story_name = None
        line_num = None
        if story is not None:
            app_uuid = story.app.app_id
            version = story.app.version
            story_name = story.name

        if line is not None:
            line_num = line['ln']

        _extra = {
            'story_name': story_name,
            'story_line': line_num
        }

        cls._sentry_client.user_context({
            'app_uuid': app_uuid,
            'app_version': version
        })

        if extra:
            _extra.update(extra)

        try:
            cls._sentry_client.captureException(extra=_extra)
        finally:
            cls._sentry_client.context.clear()
