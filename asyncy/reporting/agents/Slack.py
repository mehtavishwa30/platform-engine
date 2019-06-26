import json
import os
import re
import sys
import traceback
from os.path import join

from tornado.httpclient import AsyncHTTPClient

from asyncy import Logger
from asyncy.Exceptions import StoryscriptError
from asyncy.reporting.Agent import ReportingAgent
from asyncy.utils.HttpUtils import HttpUtils


class SlackAgent(ReportingAgent):

    def __init__(self, webhook: str, logger: Logger):
        self._webhook = webhook
        self._logger = logger
        self._http_client = AsyncHTTPClient()

    async def publish_exc(self, exc_info: Exception, exc_data: dict, agent_options=None):
        if self._webhook is None and agent_options is None:
            return

        story_name = None
        app_uuid = None
        app_version = None

        if 'app_uuid' in exc_data:
            app_uuid = f"*App UUID*: {exc_data['app_uuid']}\n"

        if 'app_version' in exc_data:
            app_version = f"*App Version*: {exc_data['app_version']}\n"

        if 'story_name' in exc_data:
            story_name = f"*Story Name*: {exc_data['story_name']}\n\n"

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
            traceback_line = f"```{root_err_str}\n\nRoot Traceback:\n{_root_traceback}\n{err_str}\n\nTraceback:\n{_traceback}```"
        else:
            traceback_line = f"```{err_str}\n\nTraceback:\n{_traceback}```"

        err_msg = f"An exception occurred with the following information:\n\n" \
            f"{app_uuid}" \
            f"{app_version}" \
            f"{story_name}" \
            f"{traceback_line}"

        webhook = self._webhook

        # allow the webhook to be overridden easily for app based reporting
        if agent_options is not None and \
                "webhook" in agent_options:
            webhook = agent_options["webhook"]

        await HttpUtils.fetch_with_retry(tries=3, logger=self._logger, url=webhook, http_client=self._http_client,
                                         kwargs={
                                             "method": "POST",
                                             "body": json.dumps({"text": err_msg}),
                                             "headers": {"Content-Type": "application/json"}
                                         })
