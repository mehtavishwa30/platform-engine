# -*- coding: utf-8 -*-
import traceback

from raven import Client

from ..ReportingAgent import ReportingAgent
from ...Exceptions import StoryscriptError
from ...Logger import Logger


class SentryAgent(ReportingAgent):
    _sentry_client = None

    def __init__(self, dsn: str, release: str, logger: Logger):
        self._release = release
        self._logger = logger

        if dsn is None:
            return

        self._sentry_client = Client(
            dsn=dsn,
            enable_breadcrumbs=False,
            install_logging_hook=False,
            hook_libraries=[],
            release=release)

    async def publish_exc(self, exc_info: BaseException,
                          exc_data: dict, agent_options=None):
        if self._sentry_client is None:
            return

        self._sentry_client.context.clear()

        app_uuid = None
        app_version = None
        app_name = None

        if 'app_name' in exc_data:
            app_name = exc_data['app_name']

        if 'app_uuid' in exc_data:
            app_uuid = exc_data['app_uuid']

        if 'app_version' in exc_data:
            app_version = exc_data['app_version']

        story_name = None
        story_line = None
        if 'story_line' in exc_data:
            story_line = exc_data['story_line']

        if 'story_name' in exc_data:
            story_name = exc_data['story_name']

        self._sentry_client.user_context({
            'platform_release': self._release,
            'app_uuid': app_uuid,
            'app_name': app_name,
            'app_version': app_version,
            'story_name': story_name,
            'story_line': story_line
        })

        _traceback = self.cleanup_traceback(
            ''.join(traceback.format_tb(exc_info.__traceback__)))

        err_str = f'{type(exc_info).__qualname__}: {exc_info}'

        # we need to pull the top level exception for reporting
        # if requested by the reporter
        _root_traceback = None
        if agent_options is not None:
            if agent_options.get('full_stacktrace', False) and \
                    type(exc_info) is StoryscriptError and \
                    exc_info.root is not None:
                _root_traceback = self.cleanup_traceback(
                    ''.join(traceback.format_tb(exc_info.root.__traceback__)))

        if _root_traceback is not None:
            root_err_str = f'{type(exc_info.root).__qualname__}: ' \
                f'{exc_info.root}'
            traceback_line = f'{root_err_str}\n\n' \
                f'Root Traceback:\n{_root_traceback}\n{err_str}\n\n' \
                f'Traceback:\n{_traceback}'
        else:
            traceback_line = f'{err_str}\n\nTraceback:\n{_traceback}'

        try:
            # we utilize captureMessage because captureException
            # will not properly work 100% of the time
            # unless this is always called within try/catch block
            self._sentry_client.captureMessage(message=traceback_line)
        finally:
            self._sentry_client.context.clear()
