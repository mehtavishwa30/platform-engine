# -*- coding: utf-8 -*-
from asyncy.Exceptions import StoryscriptError
from asyncy.Sentry import Sentry

from raven import Client


def test_init(patch):
    # noinspection PyTypeChecker
    Sentry.init(None, None)  # No-op.
    patch.init(Client)
    Sentry.init('sentry_dsn', 'release_ver')
    Client.__init__.assert_called_with(
        dsn='sentry_dsn',
        enable_breadcrumbs=False,
        install_logging_hook=False,
        hook_libraries=[],
        release='release_ver')
    # noinspection PyProtectedMember
    assert Sentry._sentry_client is not None


def test_capture_exc(patch, magic):
    patch.many(Client, ['captureException', 'user_context'])
    Sentry.init('https://foo:foo@sentry.io/123', 'release_ver')
    story = magic()
    story.app.app_id = 'app_id'
    story.app.version = 'app_version'
    story.name = 'story_name'
    line = magic()
    line['ln'] = '28'

    try:
        raise StoryscriptError(message='foo', story=story, line=line)
    except StoryscriptError as e:
        Sentry.capture_exc(e, story, line, {'foo': 'bar'})

    Client.user_context.assert_called_with({
        'app_uuid': 'app_id',
        'app_version': 'app_version'
    })

    Client.captureException.assert_called_with(extra={
        'story_line': line['ln'],
        'story_name': 'story_name',
        'foo': 'bar'
    })
