# -*- coding: utf-8 -*-
import asyncio

from .Agent import ReportingAgent
from .. import Logger
from ..Exceptions import StoryscriptError
from ..Stories import Stories
from .agents.Sentry import SentryAgent
from .agents.Slack import SlackAgent
from .agents.CleverTap import CleverTapAgent


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

        if 'slack_webhook' in config:
            cls._slack_agent = SlackAgent(webhook=config['slack_webhook'],
                                          release=release, logger=logger)

        if 'sentry_dsn' in config:
            cls._sentry_agent = SentryAgent(dsn=config['sentry_dsn'],
                                            release=release, logger=logger)

        clever_config = config.get('clevertap_config', {
            'account': None,
            'pass': None
        })

        if clever_config['account'] is not None and clever_config['pass'] is not None:
            cls._clever_agent = CleverTapAgent(account_id=clever_config['account'],
                                               account_pass=clever_config['pass'],
                                               release=release, logger=logger)


    @classmethod
    def init_app_agents(cls, app_uuid: str, config: dict, logger: Logger):
        # todo - finish this up
        return

    @classmethod
    def app_agents(cls, app_uuid: str):
        return cls._app_agents.get(app_uuid, None)

    @classmethod
    def capture_exc(cls, exc_info: BaseException,
                    story: Stories = None, line: dict = None,
                    agent_options: dict = None):
        task = cls._capture_exc(exc_info=exc_info, story=story, line=line,
                                agent_options=agent_options)
        asyncio.get_event_loop().create_task(task)

    @classmethod
    async def _capture_exc(cls, exc_info: BaseException,
                           story: Stories = None, line: dict = None,
                           agent_options: dict = None):

        if cls._logger is None:
            return

        if isinstance(exc_info, StoryscriptError):
            story = exc_info.story
            line = exc_info.line

        app_name = None
        app_uuid = None
        app_version = None
        story_name = None
        story_line = None
        if story is not None:
            app_name = story.app.app_name
            app_uuid = story.app.app_id
            app_version = story.app.version
            story_name = story.name

        if line is not None:
            story_line = line['ln']

        logger = cls._logger

        default_agent_options = {
            'full_traceback': True
        }

        if agent_options is not None:
            if 'story_name' in agent_options:
                story_name = agent_options['story_name']
                del agent_options['story_name']

            if 'story_line' in agent_options:
                story_line = agent_options['story_line']
                del agent_options['story_line']

            if 'app_name' in agent_options:
                app_name = agent_options['app_name']
                del agent_options['app_name']

            if 'app_uuid' in agent_options:
                app_uuid = agent_options['app_uuid']
                del agent_options['app_uuid']

            if 'app_version' in agent_options:
                story_line = agent_options['app_version']
                del agent_options['app_version']

            default_agent_options.update(agent_options)

        exc_data = {
            'story_name': story_name,
            'story_line': story_line,
            'app_name': app_name,
            'app_uuid': app_uuid,
            'app_version': app_version
        }

        if cls._sentry_agent is not None:
            try:
                await cls._sentry_agent.publish_exc(exc_info=exc_info,
                                                    exc_data=exc_data, agent_options=default_agent_options)
            except Exception as e:
                logger.error(f'Unhandled sentry reporting agent error: {str(e)}', e)

        if cls._slack_agent is not None:
            try:
                await cls._slack_agent.publish_exc(exc_info=exc_info,
                                                   exc_data=exc_data, agent_options=default_agent_options)
            except Exception as e:
                logger.error(f'Unhandled slack reporting agent error: {str(e)}', e)

        if cls._clever_agent is not None:
            try:
                await cls._clever_agent.publish_exc(exc_info=exc_info, exc_data=exc_data,
                                                    agent_options=default_agent_options)
            except Exception as e:
                logger.error(f'Unhandled CleverTap reporting agent error: {str(e)}', e)

        # todo call application agents. this is currently un-implemented, users will be able
        # to define their own agent configurations and report on their own end
        # if app_uuid is not None and app_uuid in cls._app_agents:
        #    app_agent = cls._app_agents[app_uuid]
        #    if type(app_agent) is ReportingAgent:
        #        app_agent.publish_exc(exc_info, exc_data)
        #    elif type(app_agent) is dict:
        #        return
