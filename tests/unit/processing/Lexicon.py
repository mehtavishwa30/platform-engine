# -*- coding: utf-8 -*-
from unittest import mock
from unittest.mock import MagicMock, Mock

from asyncy import Metrics
from asyncy.Exceptions import InvalidKeywordUsage, StoryscriptError
from asyncy.Stories import Stories
from asyncy.Types import StreamingService
from asyncy.constants.LineConstants import LineConstants
from asyncy.constants.LineSentinels import LineSentinels
from asyncy.constants.ServiceConstants import ServiceConstants
from asyncy.processing import Lexicon, Story
from asyncy.processing.Mutations import Mutations
from asyncy.processing.Services import Services
from asyncy.utils.HttpUtils import HttpUtils

import pytest
from pytest import fixture, mark

from tornado.httpclient import AsyncHTTPClient


@fixture
def line():
    return {'enter': '2', 'exit': '25', 'ln': '1',
            LineConstants.service: 'alpine',
            'command': 'echo',
            'args': ['args'], 'next': '26'}


@fixture
def story(patch, story):
    patch.many(story, ['end_line', 'resolve',
                       'context', 'next_block', 'line'])
    return story


@mark.parametrize('name', ['foo_var', None])
@mark.asyncio
async def test_lexicon_execute(patch, logger, story, line, async_mock, name):
    line['enter'] = None

    if name is not None:
        line['name'] = [name]

    output = MagicMock()
    patch.object(Services, 'execute', new=async_mock(return_value=output))
    patch.object(Lexicon, 'line_number_or_none')
    result = await Lexicon.execute(logger, story, line)
    Services.execute.mock.assert_called_with(story, line)

    if name is not None:
        story.end_line.assert_called_with(line['ln'],
                                          output=output,
                                          assign={'paths': [name]})
    else:
        story.end_line.assert_called_with(line['ln'],
                                          output=output,
                                          assign=None)
    story.line.assert_called_with(line['next'])
    assert result == Lexicon.line_number_or_none()


@mark.asyncio
async def test_lexicon_execute_none(patch, logger, story, line, async_mock):
    line['enter'] = None
    story.line.return_value = None
    patch.object(Services, 'execute', new=async_mock())
    result = await Lexicon.execute(logger, story, line)
    assert result is None


@mark.asyncio
async def test_lexicon_set(patch, logger, story):
    story.context = {}
    patch.object(Lexicon, 'line_number_or_none')
    line = {'ln': '1', 'name': ['out'], 'args': ['values'], 'next': '2'}
    story.resolve.return_value = 'resolved'
    result = await Lexicon.set(logger, story, line)
    story.resolve.assert_called_with(line['args'][0])
    story.end_line.assert_called_with(
        line['ln'], assign={'paths': ['out'], '$OBJECT': 'path'},
        output='resolved')
    story.line.assert_called_with(line['next'])
    assert result == Lexicon.line_number_or_none()


@mark.asyncio
async def test_lexicon_set_mutation(patch, logger, story):
    story.context = {}
    patch.object(Lexicon, 'line_number_or_none')
    patch.object(Mutations, 'mutate')
    line = {
        'ln': '1',
        'name': ['out'],
        'args': [
            'values',
            {
                '$OBJECT': 'mutation'
            }
        ],
        'next': '2'
    }
    Mutations.mutate.return_value = 'mutated_result'
    result = await Lexicon.set(logger, story, line)
    story.resolve.assert_called_with(line['args'][0])
    story.end_line.assert_called_with(
        line['ln'], assign={'paths': ['out'], '$OBJECT': 'path'},
        output='mutated_result')
    story.line.assert_called_with(line['next'])
    Mutations.mutate.assert_called_with(line['args'][1],
                                        story.resolve(), story, line)
    assert result == Lexicon.line_number_or_none()


@mark.asyncio
async def test_lexicon_set_invalid_operation(patch, logger, story):
    story.context = {}
    patch.object(Lexicon, 'line_number_or_none')
    line = {
        'ln': '1',
        'args': [
            'values',
            {
                '$OBJECT': 'foo'
            }
        ],
        'next': '2'
    }
    with pytest.raises(StoryscriptError):
        await Lexicon.set(logger, story, line)


@mark.asyncio
async def test_lexicon_function(patch, logger, story, line):
    patch.object(story, 'next_block')
    patch.object(Lexicon, 'line_number_or_none', return_value='1')
    assert await Lexicon.function(logger, story, line) == '1'
    story.next_block.assert_called_with(line)


@mark.parametrize('method', ['elif', 'else'])
@mark.asyncio
async def test_if_condition_elif_else(patch, logger, story, line, method):
    line['method'] = method
    patch.object(Lexicon, 'line_number_or_none')
    patch.object(story, 'next_block')
    ret = await Lexicon.if_condition(logger, story, line)
    story.next_block.assert_called_with(line)
    Lexicon.line_number_or_none.assert_called_with(story.next_block())
    assert ret == Lexicon.line_number_or_none()


@mark.asyncio
async def test_if_condition_1(patch, logger, magic):
    tree = {
        '1': {
            'ln': '1',
            'method': 'if',
            'parent': None,
            'enter': '2',
            'next': '2'
        },
        '2': {
            'ln': '2',
            'parent': '1',
            'next': None
        }
    }

    patch.object(Lexicon, '_is_if_condition_true', return_value=False)
    patch.object(Lexicon, 'line_number_or_none')
    story = Stories(magic(), 'foo', logger)

    story.tree = tree
    ret = await Lexicon.if_condition(logger, story, tree['1'])
    assert ret is None


@mark.asyncio
async def test_if_condition_2(patch, logger, magic):
    tree = {
        '1': {
            'ln': '1',
            'method': 'if',
            'enter': '2',
            'next': '2'
        },
        '2': {
            'ln': '2',
            'parent': '1',
            'next': '3'
        },
        '3': {
            'ln': '3',
            'next': None,
            'method': 'execute'
        }
    }

    patch.object(Lexicon, '_is_if_condition_true', return_value=False)
    story = Stories(magic(), 'foo', logger)

    story.tree = tree
    ret = await Lexicon.if_condition(logger, story, tree['1'])
    assert ret == '3'


def test__is_if_condition_true(patch, story):
    line = {
        'args': ['my_condition']
    }
    patch.object(story, 'resolve', return_value='condition_result')
    assert Lexicon._is_if_condition_true(story, line) == 'condition_result'
    story.resolve.assert_called_with('my_condition', encode=False)


def test__is_if_condition_true_complex(patch, story):
    line = {
        'args': ['my_condition', 'my_condition_2']
    }
    with pytest.raises(StoryscriptError):
        Lexicon._is_if_condition_true(story, line)


@mark.parametrize('case', [
    # case[0] - side_effect for Lexicon._is_if_condition_true
    # case[1] - expected line number to be returned
    [[True, False, False], '2'],
    [[False, True, False], '4'],
    [[False, False, True], '6'],
    [[False, False, False], '8'],
])
@mark.asyncio
async def test_if_condition(patch, logger, magic, case):
    tree = {
        '1': {
            'ln': '1',
            'method': 'if',
            'parent': None,
            'enter': '2',
            'next': '2'
        },
        '2': {
            'ln': '2',
            'parent': '1',
            'next': '3'
        },
        '3': {
            'ln': '3',
            'method': 'elif',
            'parent': None,
            'enter': '4',
            'next': '4'
        },
        '4': {
            'ln': '4',
            'parent': '3',
            'next': '5'
        },
        '5': {
            'ln': '5',
            'method': 'elif',
            'parent': None,
            'enter': '6',
            'next': '6'
        },
        '6': {
            'ln': '6',
            'parent': '5',
            'next': '7'
        },
        '7': {
            'ln': '7',
            'method': 'else',
            'parent': None,
            'next': '8',
            'enter': '8'
        },
        '8': {
            'ln': '8',
            'parent': '7',
            'next': None
        }
    }

    patch.object(Lexicon, '_is_if_condition_true', side_effect=case[0])
    story = Stories(magic(), 'foo', logger)

    story.tree = tree
    ret = await Lexicon.if_condition(logger, story, tree['1'])
    assert ret == case[1]


@mark.parametrize('valid_usage', [True, False])
@mark.asyncio
async def test_break(logger, story, line, patch, valid_usage):
    patch.object(Lexicon, '_does_line_have_parent_method',
                 return_value=valid_usage)
    if valid_usage:
        ret = await Lexicon.break_(logger, story, line)
        assert ret == LineSentinels.BREAK
        Lexicon._does_line_have_parent_method.assert_called_with(
            story, line, 'for')
    else:
        with pytest.raises(InvalidKeywordUsage):
            await Lexicon.break_(logger, story, line)


def test_lexicon_unless(logger, story, line):
    story.context = {}
    result = Lexicon.unless_condition(logger, story, line)
    logger.log.assert_called_with('lexicon-unless', line, story.context)
    story.resolve.assert_called_with(line['args'][0], encode=False)
    assert result == line['exit']


def test_lexicon_unless_false(logger, story, line):
    story.context = {}
    story.resolve.return_value = False
    assert Lexicon.unless_condition(logger, story, line) == line['enter']


@mark.parametrize('execute_block_return',
                  [LineSentinels.BREAK, LineSentinels.RETURN, None])
@mark.asyncio
async def test_lexicon_for_loop(patch, logger, story, line,
                                async_mock, execute_block_return):
    iterated_over_items = []

    async def execute_block(our_logger, our_story, our_line):
        iterated_over_items.append(story.context['element'])
        assert our_logger == logger
        assert our_story == story
        assert our_line == line
        return execute_block_return

    patch.object(Lexicon, 'execute', new=async_mock())
    patch.object(Lexicon, 'line_number_or_none')
    patch.object(Story, 'execute_block', side_effect=execute_block)
    patch.object(story, 'next_block')

    line['args'] = [
        {'$OBJECT': 'path', 'paths': ['elements']}
    ]

    line['output'] = ['element']
    story.context = {'elements': ['one', 'two', 'three']}
    story.resolve.return_value = ['one', 'two', 'three']
    story.environment = {}
    result = await Lexicon.for_loop(logger, story, line)

    if execute_block_return == LineSentinels.BREAK:
        assert iterated_over_items == ['one']
        assert result == Lexicon.line_number_or_none(story.next_block(line))
    elif LineSentinels.is_sentinel(execute_block_return):
        assert iterated_over_items == ['one']
        assert result == execute_block_return
    else:
        assert iterated_over_items == story.context['elements']
        assert result == Lexicon.line_number_or_none(story.next_block(line))

    # Ensure no leakage of the element
    assert story.context.get('element') is None


@mark.asyncio
async def test_lexicon_execute_streaming_container(patch, story, async_mock):
    line = {
        'enter': '10',
        'ln': '9',
        LineConstants.service: 'foo',
        'output': 'output',
        'next': '11'
    }

    patch.object(Services, 'start_container', new=async_mock())
    patch.object(Lexicon, 'line_number_or_none')
    patch.many(story, ['end_line', 'line'])
    Metrics.container_start_seconds_total = Mock()
    ret = await Lexicon.execute(story.logger, story, line)
    Services.start_container.mock.assert_called_with(story, line)
    story.end_line.assert_called_with(
        line['ln'], output=Services.start_container.mock.return_value,
        assign={'paths': line.get('output')})
    Metrics.container_start_seconds_total.labels().observe.assert_called_once()
    story.line.assert_called_with(line['next'])
    Lexicon.line_number_or_none.assert_called_with(story.line())
    assert ret == Lexicon.line_number_or_none()


@mark.asyncio
async def test_story_execute_function(patch, logger, story, async_mock):
    line = {'function': 'my_super_awesome_function'}
    patch.many(story, ['function_line_by_name',
                       'context_for_function_call', 'set_context'])
    patch.object(Story, 'execute_block', new=async_mock())
    first_context = {'first': 'context'}

    story.context = first_context
    await Lexicon.call(logger, story, line)

    story.function_line_by_name.assert_called_with(line['function'])
    story.context_for_function_call \
        .assert_called_with(line, story.function_line_by_name())

    assert story.set_context.mock_calls == [
        mock.call(story.context_for_function_call()),
        mock.call(first_context)
    ]

    Story.execute_block.mock \
        .assert_called_with(logger, story, story.function_line_by_name())


@mark.parametrize('service_name', ['http', 'unknown_service'])
@mark.asyncio
async def test_lexicon_when(patch, story, async_mock, service_name):
    ss = StreamingService(name='name', command='command',
                          container_name='container_name', hostname='hostname')
    if service_name == 'unknown_service':
        ss = 'foo'

    line = {
        LineConstants.service: 'http'
    }

    story.context = {
        'http': ss
    }

    patch.object(story, 'next_block')

    patch.object(Services, 'when', new=async_mock())
    patch.object(Lexicon, 'line_number_or_none')

    if service_name == 'unknown_service':
        with pytest.raises(StoryscriptError):
            await Lexicon.when(story.logger, story, line)
    else:
        ret = await Lexicon.when(story.logger, story, line)
        story.next_block.assert_called_with(line)
        Lexicon.line_number_or_none.assert_called_with(
            story.next_block.return_value)
        assert ret == Lexicon.line_number_or_none.return_value


@mark.asyncio
async def test_return_in_when(patch, logger, story):
    tree = {
        '1': {'ln': '1', 'method': 'when'},
        '2': {'ln': '2', 'method': 'execute', 'parent': '1'},
        '3': {'ln': '3', 'method': 'if', 'parent': '1'},
        '4': {'ln': '4', 'method': 'return', 'parent': '2'},
        '5': {'ln': '5', 'method': 'execute'},
    }

    def get_line(ln):
        return tree[ln]

    patch.object(story, 'line', side_effect=get_line)
    patch.object(story, 'next_block', return_value=tree['5'])
    patch.object(Lexicon, 'line_number_or_none')

    story.tree = tree

    ret = await Lexicon.ret(logger, story, tree['4'])

    assert ret == LineSentinels.RETURN


@mark.asyncio
async def test_return_used_outside_when(patch, logger, story):
    tree = {
        '1': {'ln': '1', 'method': 'return'},
    }
    with pytest.raises(StoryscriptError):
        await Lexicon.ret(logger, story, tree['1'])


@mark.asyncio
async def test_return_used_with_args(patch, logger, story):
    tree = {
        '1': {'ln': '1', 'method': 'return', 'args': [{}]},
    }
    with pytest.raises(StoryscriptError):
        await Lexicon.ret(logger, story, tree['1'])


def test_next_line_or_none():
    line = {'ln': '10'}
    assert Lexicon.line_number_or_none(line) == '10'
    assert Lexicon.line_number_or_none(None) is None


@mark.asyncio
async def test_lexicon_when_invalid(story):
    line = {'service': 'foo', 'command': 'bar'}
    with pytest.raises(StoryscriptError):
        await Lexicon.when(story.logger, story, line)
