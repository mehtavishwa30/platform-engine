# -*- coding: utf-8 -*-
import asyncio

from asyncy.Exceptions import StoryscriptError
from asyncy.reporting.Reporter import ExceptionReporter
from asyncy.reporting.agents.CleverTap import CleverTapAgent
from asyncy.reporting.agents.Sentry import SentryAgent
from asyncy.reporting.agents.Slack import SlackAgent

import pytest


def test_init(patch):
    patch.init(SentryAgent)
    patch.init(SlackAgent)
    patch.init(CleverTapAgent)

    ExceptionReporter.init({
        'sentry_dsn': 'sentry_dsn',
        'slack_webhook': 'slack_webhook',
        'clevertap_config': {
            'account': 'account',
            'pass': 'pass'
        },
        'user_reporting': False,
        'user_reporting_stacktrace': False
    }, 'release', 'logger')

    SentryAgent.__init__.assert_called_with(
        dsn='sentry_dsn',
        release='release',
        logger='logger')

    SlackAgent.__init__.assert_called_with(
        webhook='slack_webhook',
        release='release',
        logger='logger'
    )

    CleverTapAgent.__init__.assert_called_with(
        account_id='account',
        account_pass='pass',
        release='release',
        logger='logger'
    )

    assert ExceptionReporter._sentry_agent is not None
    assert ExceptionReporter._slack_agent is not None
    assert ExceptionReporter._clever_agent is not None


@pytest.mark.asyncio
async def test_capture_exc(patch, magic):
    ExceptionReporter.init({
        'sentry_dsn': 'https://foo:foo@sentry.io/123',
        'slack_webhook': 'slack_webhook',
        'clevertap_config': {
            'account': 'account',
            'pass': 'pass'
        },
        'user_reporting': False,
        'user_reporting_stacktrace': False
    }, 'release', 'logger')

    patch.object(SentryAgent, 'publish_exc',
                 return_value=asyncio.sleep(1e-3))
    patch.object(SlackAgent, 'publish_exc',
                 return_value=asyncio.sleep(1e-3))
    patch.object(CleverTapAgent, 'publish_exc',
                 return_value=asyncio.sleep(1e-3))

    story = magic()
    story.app.app_name = 'app_name'
    story.app.app_id = 'app_id'
    story.app.version = 'app_version'
    story.name = 'story_name'
    line = magic()
    line['ln'] = '28'

    try:
        raise StoryscriptError(message='foo', story=story, line=line)
    except StoryscriptError as e:
        await ExceptionReporter._capture_exc(
            exc_info=e,
            story=story, line=line,
            agent_options={
                'clever_ident': 'foo@foo.com',
                'clever_event': 'Event',
                'allow_user_agents': False
            })

        exc_data = {
            'app_uuid': story.app.app_id,
            'app_name': story.app.app_name,
            'app_version': story.app.version,
            'story_line': line['ln'],
            'story_name': story.name,
            'platform_release': 'release'
        }

        agent_options = {
            'clever_ident': 'foo@foo.com',
            'clever_event': 'Event',
            'full_stacktrace': True
        }

        SentryAgent.publish_exc.assert_called_with(
            exc_info=e,
            exc_data=exc_data,
            agent_options=agent_options)

        SlackAgent.publish_exc.assert_called_with(
            exc_info=e,
            exc_data=exc_data,
            agent_options=agent_options)

        CleverTapAgent.publish_exc.assert_called_with(
            exc_info=e,
            exc_data=exc_data,
            agent_options=agent_options)


@pytest.mark.asyncio
async def test_capture_exc_with_user_agents(patch, magic):
    ExceptionReporter.init({
        'slack_webhook': 'non_user_webhook',
        'user_reporting': True,
        'user_reporting_stacktrace': False
    }, 'release', 'logger')

    ExceptionReporter.init_app_agents('user_app_id', {
        'slack_webhook': 'user_webhook'
    })

    # 2 sleep coroutines for await
    patch.object(SlackAgent, 'publish_exc',
                 side_effect=[
                     asyncio.sleep(1e-3),
                     asyncio.sleep(1e-3)
                 ])

    story = magic()
    story.app.app_name = 'app_name'
    story.app.app_id = 'user_app_id'
    story.app.version = 'app_version'
    story.name = 'story_name'
    line = magic()
    line['ln'] = '28'

    try:
        raise StoryscriptError(message='foo', story=story, line=line)
    except StoryscriptError as e:
        # capture_exc is a simple wrapper for _capture_exc which is async
        await ExceptionReporter._capture_exc(
            exc_info=e,
            story=story,
            line=line,
            agent_options={
                'allow_user_agents': True
            })

        exc_data = {
            'app_uuid': story.app.app_id,
            'app_name': story.app.app_name,
            'app_version': story.app.version,
            'story_line': line['ln'],
            'story_name': story.name,
            'platform_release': 'release'
        }

        # system based reporting
        SlackAgent.publish_exc.assert_any_call(
            exc_info=e,
            exc_data=exc_data,
            agent_options={
                'full_stacktrace': True
            })

        # the user agent call
        SlackAgent.publish_exc.assert_any_call(
            exc_info=e,
            exc_data=exc_data,
            agent_options={
                'full_stacktrace': False,
                'no_stacktrace': True,
                'webhook': 'user_webhook'
            })
