# -*- coding: utf-8 -*-
import asyncio

from raven.transport import tornado

from .Agent import ReportingAgent
from .. import Logger
from ..Exceptions import StoryscriptError
from ..Stories import Stories
from ..reporting.agents.Sentry import SentryAgent
from ..reporting.agents.Slack import SlackAgent


class ExceptionReporter:
    _config = None
    _logger = None
    _release = None

    # agents
    _sentry_agent = None
    _slack_agent = None
    _clever_agent = None

    # create a dictionary for the storage
    # of app based agent options. this allows users
    # to create reporting agents for specific apps
    _app_agents = {}

    @classmethod
    def init(cls, config: dict, release: str, logger: Logger):
        cls._config = config
        cls._release = release
        cls._logger = logger

        if "slack_webhook" in config:
            cls._slack_agent = SlackAgent(config["slack_webhook"], logger)

        if "sentry_dsn" in config:
            cls._sentry_agent = SentryAgent(config["sentry_dsn"], release)

    @classmethod
    def init_app_agents(cls, app_uuid: str, config: dict, logger: Logger):
        #todo - finish this up
        return

    @classmethod
    def app_agents(cls, app_uuid: str):
        return cls._app_agents.get(app_uuid, None)

    @classmethod
    def capture_exc(cls, exc_info: Exception,
                    story: Stories = None, line: dict = None,
                    extra: dict = None):
        task = cls._capture_exc(exc_info=exc_info, story=story, line=line, extra=extra)
        asyncio.get_event_loop().create_task(task)

    @classmethod
    async def _capture_exc(cls, exc_info: Exception,
                           story: Stories = None, line: dict = None,
                           extra: dict = None):

        if cls._logger is None:
            return

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

        exc_data = {
            'story_name': story_name,
            'story_line': line_num,
            'app_uuid': app_uuid,
            'app_version': version
        }

        logger = cls._logger

        if extra:
            exc_data.update(extra)

            if cls._sentry_agent is not None:
                try:
                    await cls._sentry_agent.publish_exc(exc_info=exc_info,
                                                        exc_data=exc_data, agent_options={
                            "full_traceback": True
                        })
                except Exception as e:
                    logger.error(f'Unhandled sentry reporting agent error: {str(e)}', e)

            if cls._slack_agent is not None:
                try:
                    await cls._slack_agent.publish_exc(exc_info=exc_info,
                                                       exc_data=exc_data, agent_options={
                            "full_traceback": True
                        })
                except Exception as e:
                    logger.error(f'Unhandled slack reporting agent error: {str(e)}', e)

            if cls._clever_agent is not None:
                try:
                    await cls._clever_agent.publish_exc(exc_info=exc_info, exc_data=exc_data)
                except Exception as e:
                    logger.error(f'Unhandled CleverTap reporting agent error: {str(e)}', e)

        # todo call application agents. this is currently un-implemented, users will be able
        # to define their own agent configurations and report on their own end
        #if app_uuid is not None and app_uuid in cls._app_agents:
        #    app_agent = cls._app_agents[app_uuid]
        #    if type(app_agent) is ReportingAgent:
        #        app_agent.publish_exc(exc_info, exc_data)
        #    elif type(app_agent) is dict:
        #        return
