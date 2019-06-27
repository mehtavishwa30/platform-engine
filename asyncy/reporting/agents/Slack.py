import json
import traceback


from tornado.httpclient import AsyncHTTPClient

from ..Agent import ReportingAgent
from ...Exceptions import StoryscriptError
from ...Logger import Logger
from ...utils.HttpUtils import HttpUtils


class SlackAgent(ReportingAgent):

    def __init__(self, webhook: str, release: str, logger: Logger):
        self._webhook = webhook
        self._release = release
        self._logger = logger
        self._http_client = AsyncHTTPClient()

    async def publish_exc(self, exc_info: BaseException,
                          exc_data: dict, agent_options=None):
        if self._webhook is None and \
                agent_options is None:
            return

        story_name = ''
        story_line = ''
        app_uuid = ''
        app_version = ''
        app_name = ''

        if 'app_name' in exc_data:
            app_name = f'*App Name*: {exc_data["app_name"]}\n'

        if 'app_uuid' in exc_data:
            app_uuid = f'*App UUID*: {exc_data["app_uuid"]}\n'

        if 'app_version' in exc_data:
            app_version = f'*App Version*: {exc_data["app_version"]}\n'

        if 'story_name' in exc_data:
            story_name = f'*Story Name*: {exc_data["story_name"]}\n'

        if 'story_line' in exc_data:
            story_line = f'*Story Line Number*: {exc_data["story_line"]}\n\n'

        _traceback = self.cleanup_traceback(
            ''.join(traceback.format_tb(exc_info.__traceback__)))

        err_str = f'{type(exc_info).__qualname__}: {exc_info}'

        # we need to pull the top level exception for
        # reporting if requested by the reporter
        _root_traceback = None
        _full_stacktrace = True
        if agent_options is not None:
            if agent_options.get('full_stacktrace', False) and \
                    type(exc_info) is StoryscriptError and\
                    exc_info.root is not None:
                _root_traceback = self.cleanup_traceback(
                    ''.join(traceback.format_tb(exc_info.root.__traceback__)))

        if _root_traceback is not None:
            root_err_str = f'{type(exc_info.root).__qualname__}:' \
                f' {exc_info.root}'
            traceback_line = f'```{root_err_str}\n\nRoot Traceback:\n' \
                f'{_root_traceback}\n{err_str}\n\nTraceback:\n{_traceback}```'
        else:
            traceback_line = f'```{err_str}\n\nTraceback:\n{_traceback}```'

        if agent_options is not None and \
                agent_options.get('no_stacktrace', False):
            # generally we won't be reporting the
            # full error message without a full
            # stacktrace
            if _full_stacktrace and type(
                    exc_info) is StoryscriptError and \
                    exc_info.root is not None:
                traceback_line = f'*Error*: {exc_info}: {exc_info.root}'
            else:
                traceback_line = f'*Error*: {exc_info}'

        err_msg = f'An exception occurred with' \
            f' the following information:\n\n' \
            f'*Platform Engine Release*: {self._release}\n' \
            f'{app_name}' \
            f'{app_uuid}' \
            f'{app_version}' \
            f'{story_name}' \
            f'{story_line}' \
            f'{traceback_line}'

        webhook = self._webhook

        # allow the webhook to be overridden for user based reporting
        if agent_options is not None and \
                'webhook' in agent_options:
            webhook = agent_options['webhook']
        elif webhook is None:
            return

        await HttpUtils.fetch_with_retry(
            tries=3, logger=self._logger,
            url=webhook, http_client=self._http_client,
            kwargs={
                'method': 'POST',
                'body': json.dumps({'text': err_msg}),
                'headers': {'Content-Type': 'application/json'}
            })
