# -*- coding: utf-8 -*-
from asyncy.Logger import Logger

from frustum import Frustum

from pytest import fixture


@fixture
def logger(patch, config):
    patch.object(Frustum, '__init__', return_value=None)
    return Logger(config)


def test_logger_init(logger, config):
    level = config.logger['level']
    name = config.logger['name']
    Frustum.__init__.assert_called_with(name, level)


def test_logger_events(logger):
    message = 'Container {} is running'
    assert logger.events[0] == ('container-start', 'info', message)

    message = 'Container {} has finished'
    assert logger.events[1] == ('container-end', 'info', message)

    message = 'Start processing story "{}" for app {} with id {}'
    assert logger.events[2] == ('story-start', 'info', message)

    message = 'Saved results of story "{}" for app {}'
    assert logger.events[3] == ('story-save', 'info', message)

    message = 'Finished processing story "{}" for app {} with id {}'
    assert logger.events[4] == ('story-end', 'info', message)

    message = 'Received task for app {} with story "{}"'
    assert logger.events[5] == ('task-received', 'info', message)

    message = 'Created volume {}'
    assert logger.events[6] == ('container-volume', 'debug', message)

    assert logger.events[7] == ('jwt-token', 'debug', 'Encoded token: {}')
    assert logger.events[8] == ('story-parse', 'debug', 'Parsed story {}')

    message = 'Resolved "{}" to "{}"'
    assert logger.events[9] == ('story-resolve', 'debug', message)


def test_logger_start(patch, logger):
    patch.object(Frustum, 'register_event')
    patch.object(Frustum, 'start_logger')
    logger.events = [('event', 'level', 'message')]
    logger.start()
    Frustum.register_event.assert_called_with('event', 'level', 'message')
    Frustum.start_logger.assert_called_with()


def test_logger_log(patch, logger):
    patch.object(Frustum, 'log')
    logger.log('my-event')
    Frustum.log.assert_called_with('my-event')


def test_logger_log_args(patch, logger):
    patch.object(Frustum, 'log')
    logger.log('my-event', 'extra', 'args')
    Frustum.log.assert_called_with('my-event', 'extra', 'args')
