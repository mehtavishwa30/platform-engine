# -*- coding: utf-8 -*-
import traceback

from raven import Client

from ...Exceptions import StoryscriptError

from ..Agent import ReportingAgent


class SentryAgent(ReportingAgent):
    _sentry_client = None

    def __init__(self, dsn: str, release: str):
        if dsn is None:
            return

        self._sentry_client = Client(
            dsn=dsn,
            enable_breadcrumbs=False,
            install_logging_hook=False,
            hook_libraries=[],
            release=release)

    async def publish_exc(self, exc_info: Exception, exc_data: dict, agent_options=None):
        if self._sentry_client is None:
            return

        self._sentry_client.context.clear()

        app_uuid = None
        app_version = None
        if 'app_uuid' in exc_data:
            app_uuid = exc_data['app_uuid']

        if 'app_version' in exc_data:
            app_version = exc_data['app_version']

        story_name = None
        story_line = None

        if 'story_line' in exc_data:
            story_line = exc_data['story_line']

        if 'story_name' in exc_data:
            story_line = exc_data['story_name']

        self._sentry_client.user_context({
            "app_uuid": app_uuid,
            "app_version": app_version,
            "story_name": story_name,
            "story_line": story_line
        })

        _traceback = self.cleanup_traceback(''.join(traceback.format_tb(exc_info.__traceback__)))

        err_str = f'{type(exc_info).__qualname__}: {exc_info}'

        # we need to pull the top level exception for reporting if requested by the reporter
        _root_traceback = None
        if agent_options is not None:
            if agent_options.get("full_traceback", False) and type(
                    exc_info) is StoryscriptError and exc_info.root_exc is not None:
                _root_traceback = self.cleanup_traceback \
                    (''.join(traceback.format_tb(exc_info.root_exc.__traceback__)))

        if _root_traceback is not None:
            root_err_str = f'{type(exc_info.root_exc).__qualname__}: {exc_info.root_exc}'
            traceback_line = f"{root_err_str}\n\nRoot Traceback:\n{_root_traceback}\n{err_str}\n\nTraceback:\n{_traceback}"
        else:
            traceback_line = f"{err_str}\n\nTraceback:\n{_traceback}"

        try:
            # we utilize captureMessage because captureException will not properly work 100% of the time
            # unless this is always called within try/catch block
            self._sentry_client.captureMessage(message=traceback_line)
        finally:
            self._sentry_client.context.clear()
