# -*- coding: utf-8 -*-
import asyncio

from .agents.CleverTapAgent import CleverTapAgent
from .agents.SentryAgent import SentryAgent
from .agents.SlackAgent import SlackAgent
from .. import Logger
from ..Exceptions import StoryscriptError
from ..Stories import Stories


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

        # we don't check if the value is none, because users will still
        # be able to provide their own app webhook for reporting
        if 'slack_webhook' in config:
            cls._slack_agent = SlackAgent(
                webhook=config['slack_webhook'],
                release=release,
                logger=logger)

        if 'sentry_dsn' in config:
            cls._sentry_agent = SentryAgent(
                dsn=config['sentry_dsn'],
                release=release,
                logger=logger)

        clever_config = config.get('clevertap_config', {
            'account': None,
            'pass': None
        })

        if clever_config['account'] is not None and \
                clever_config['pass'] is not None:
            cls._clever_agent = CleverTapAgent(
                account_id=clever_config['account'],
                account_pass=clever_config['pass'],
                release=release, logger=logger)

    @classmethod
    def init_app_agents(cls, app_uuid: str, config: dict):
        # slack is currently the only supported user agent
        cls._app_agents[app_uuid] = {
            'slack_webhook': config.get('slack_webhook', None)
        }
        return

    @classmethod
    def app_agents(cls, app_uuid: str):
        return cls._app_agents.get(app_uuid, None)

    @classmethod
    def capture_exc(cls, exc_info: BaseException,
                    agent_options: dict = None):
        task = cls._capture_exc(
            exc_info=exc_info,
            agent_options=agent_options
        )
        asyncio.get_event_loop().create_task(task)

    @classmethod
    async def _capture_exc(cls, exc_info: BaseException,
                           agent_options: dict = None):

        if cls._logger is None:
            return

        story = None
        line = None
        app_name = None
        app_uuid = None
        app_version = None
        story_name = None
        story_line = None

        if isinstance(exc_info, StoryscriptError) and \
                hasattr(exc_info, 'story') and \
                hasattr(exc_info, 'line'):
            story = exc_info.story
            line = exc_info.line

        if story is not None:
            app_name = story.app.app_name
            app_uuid = story.app.app_id
            app_version = story.app.version
            story_name = story.name

        if line is not None:
            story_line = line['ln']

        logger = cls._logger

        default_agent_options = {
            'full_stacktrace': True
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
                app_version = agent_options['app_version']
                del agent_options['app_version']

            default_agent_options.update(agent_options)

        del default_agent_options['allow_user_agents']

        exc_data = {
            'story_name': story_name,
            'story_line': story_line,
            'app_name': app_name,
            'app_uuid': app_uuid,
            'app_version': app_version,
            'platform_release': cls._release
        }

        if cls._sentry_agent is not None:
            try:
                await cls._sentry_agent.publish_exc(
                    exc_info=exc_info,
                    exc_data=exc_data,
                    agent_options=default_agent_options)
            except Exception as e:
                logger.error(
                    f'Unhandled sentry reporting agent error: {str(e)}', e)

        if cls._slack_agent is not None:
            try:
                await cls._slack_agent.publish_exc(
                    exc_info=exc_info,
                    exc_data=exc_data,
                    agent_options=default_agent_options)
            except Exception as e:
                logger.error(
                    f'Unhandled slack reporting agent error: {str(e)}', e)

        if cls._clever_agent is not None:
            try:
                await cls._clever_agent.publish_exc(
                    exc_info=exc_info, exc_data=exc_data,
                    agent_options=default_agent_options)
            except Exception as e:
                logger.error(
                    f'Unhandled CleverTap reporting agent error: {str(e)}', e)

        # this is disabled at the top level
        if cls._config.get('user_reporting', False) is False:
            return

        # ensure that this exception should be pushed to users
        if agent_options is not None and \
                agent_options.get('allow_user_agents', False):
            if app_uuid is not None and \
                    app_uuid in cls._app_agents:
                app_agent_config = cls._app_agents[app_uuid]
                if cls._slack_agent is not None and \
                        'slack_webhook' in app_agent_config:
                    try:
                        user_agent_options = \
                            default_agent_options.copy()

                        user_agent_options['webhook'] = \
                            app_agent_config['slack_webhook']

                        if cls._config. \
                                get('user_reporting_stacktrace',
                                    False) is False:
                            user_agent_options['full_stacktrace'] = False
                            user_agent_options['no_stacktrace'] = True
                        else:
                            user_agent_options['full_stacktrace'] = True

                        await cls._slack_agent.publish_exc(
                            exc_info=exc_info,
                            exc_data=exc_data,
                            agent_options=user_agent_options)
                    except Exception as e:
                        logger.error(
                            f'Unhandled slack '
                            f'reporting agent '
                            f'error: {str(e)}',
                            e)
