import json
import time
import traceback

from tornado.httpclient import AsyncHTTPClient

from ..ReportingAgent import ReportingAgent
from ...Exceptions import StoryscriptError
from ...Logger import Logger
from ...utils.HttpUtils import HttpUtils


class CleverTapAgent(ReportingAgent):

    def __init__(self, account_id: str,
                 account_pass: str,
                 release: str,
                 logger: Logger):
        self._account_id = account_id
        self._account_pass = account_pass
        self._release = release
        self._logger = logger
        self._http_client = AsyncHTTPClient()

    async def publish_exc(self, exc_info: BaseException,
                          exc_data: dict,
                          agent_options=None):
        if agent_options is None or \
                'clever_ident' not in agent_options or \
                'clever_event' not in agent_options:
            return

        _traceback = self.cleanup_traceback(
            ''.join(traceback.format_tb(exc_info.__traceback__)))

        err_str = f'{type(exc_info).__qualname__}: {exc_info}'

        _root_traceback = None
        if agent_options is not None:
            if agent_options.get('full_stacktrace', False) and type(
                    exc_info) is StoryscriptError and \
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

        evt_data = {
            'Stacktrace': traceback_line
        }

        if 'app_name' in exc_data:
            evt_data['App Name'] = exc_data['app_name']

        if 'app_version' in exc_data:
            evt_data['App Version'] = exc_data['app_version']

        if 'story_name' in exc_data:
            evt_data['Story name'] = exc_data['story_name']

        if 'story_line' in exc_data:
            evt_data['Story Line'] = exc_data['story_line']

        event = {
            'ts': time.time(),
            'identity': agent_options['clever_ident'],
            'evtName': agent_options['clever_event'],
            'evtData': evt_data
        }

        await HttpUtils.fetch_with_retry(
            tries=3, logger=self._logger,
            url='https://api.clevertap.com/1/upload',
            http_client=self._http_client,
            kwargs={
                'method': 'POST',
                'body': json.dumps({'d': [event]}),
                'headers': {
                    'X-CleverTap-Account-Id': self._account_id,
                    'X-CleverTap-Passcode': self._account_pass,
                    'Content-Type': 'application/json; charset=utf-8'
                }
            })
