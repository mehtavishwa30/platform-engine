# -*- coding: utf-8 -*-
import pathlib
import time

from asyncy.Stories import MAX_BYTES_LOGGING, Stories
from asyncy.utils import Dict, Resolver

from pytest import mark


def test_stories_init(app, logger, story):
    assert story.entrypoint == app.stories['hello.story']['entrypoint']
    assert story.app == app
    assert story.name == 'hello.story'
    assert story.logger == logger
    assert story.execution_id is not None
    assert story.results == {}


def test_new_frame(story):
    with story.new_frame('10'):
        current_stack = story.get_stack()
        assert len(current_stack) == 1
        assert current_stack[0] == '10'

    current_stack = story.get_stack()
    assert len(current_stack) == 0


def test_new_frame_stack_does_not_unwind_on_exception(story):
    try:
        with story.new_frame('10'):
            raise IOError()
    except IOError:
        current_stack = story.get_stack()
        assert len(current_stack) == 1
        assert current_stack[0] == '10'


def test_stories_get_tmp_dir(story):
    story.execution_id = 'ex'
    assert story.get_tmp_dir() == '/tmp/story.ex'


def test_stories_create_tmp_dir(patch, story):
    patch.object(pathlib, 'Path')
    patch.object(story, 'get_tmp_dir')

    # Yes, called twice to ensure the dir is created just once.
    story.create_tmp_dir()
    story.create_tmp_dir()

    story.get_tmp_dir.assert_called_once()

    pathlib.Path.assert_called_with(story.get_tmp_dir())
    pathlib.Path().mkdir.assert_called_with(
        parents=True, mode=0o700, exist_ok=True)


@mark.parametrize('long', [True, False])
def test_get_str_for_logging(long):
    def make_string(length):
        out = ''
        for i in range(0, length):
            out += 'a'
        return out

    test_str = 'hello world'
    if long:
        test_str = make_string(1024)

    actual_val = Stories.get_str_for_logging(test_str)

    if long:
        assert actual_val == f'{test_str[:MAX_BYTES_LOGGING]} ... ' \
                             f'({1024-MAX_BYTES_LOGGING} bytes truncated)'
    else:
        assert actual_val == 'hello world'


def test_stories_line(magic, story):
    story.tree = magic()
    line = story.line('1')
    assert line == story.tree['1']


def test_stories_line_none(magic, story):
    story.tree = magic()
    line = story.line(None)
    assert line is None


def test_stories_first_line(patch, story):
    story.entrypoint = '16'
    story.tree = {'23': {'ln': '23'}, '16': {'ln': '16'}}
    result = story.first_line()
    assert result == '16'


def test_stories_function_line_by_name(patch, story):
    patch.object(story, 'line')
    ret = story.function_line_by_name('execute')
    story.line.assert_called_with(
        story.app.stories[story.name]['functions']['execute'])

    assert ret == story.line()


def test_stories_resolve(patch, logger, story):
    patch.object(Resolver, 'resolve')
    story.context = 'context'
    result = story.resolve('args')
    assert result == 'args'


def test_command_arguments_list(patch, story):
    patch.object(Stories, 'resolve', return_value='something')
    obj = {'$OBJECT': 'string', 'string': 'string'}
    result = story.command_arguments_list([obj])
    Stories.resolve.assert_called_with(obj, encode=True)
    assert result == ['something']


def test_command_arguments_list_none(patch, story):
    """
    Ensures that when an argument resolves to None it is used literally
    """
    patch.object(Stories, 'resolve', return_value=None)
    obj = {'$OBJECT': 'path', 'paths': ['literal']}
    result = story.command_arguments_list([obj])
    Stories.resolve.assert_called_with(obj)
    assert result == ['literal']


def test_stories_start_line(patch, story):
    patch.object(time, 'time')
    story.start_line('1')
    assert story.results['1'] == {'start': time.time()}


def test_stories_end_line(patch, story):
    patch.object(time, 'time')
    story.results = {'1': {'start': 'start'}}
    story.end_line('1')
    assert story.results['1']['output'] is None
    assert story.results['1']['end'] == time.time()
    assert story.results['1']['start'] == 'start'


def test_stories_end_line_output(patch, story):
    patch.object(time, 'time')
    story.results = {'1': {'start': 'start'}}
    story.end_line('1', output='output')
    assert story.results['1']['output'] == 'output'


def test_stories_end_line_output_assign(patch, story):
    patch.object(Dict, 'set')
    story.results = {'1': {'start': 'start'}}
    assign = {'paths': ['x']}
    story.end_line('1', output='output', assign=assign)
    assert story.results['1']['output'] == 'output'
    Dict.set.assert_called_with(story.context, assign['paths'], 'output')


def test_stories_end_line_output_as_list(patch, story):
    patch.object(time, 'time')
    story.results = {'1': {'start': 'start'}}
    story.end_line('1', output=['a', 'b'])
    assert story.results['1']['output'] == ['a', 'b']


def test_stories_end_line_output_as_json_no_auto_convert(patch, story):
    patch.object(time, 'time')
    story.results = {'1': {'start': 'start'}}
    story.end_line('1', output='{"key":"value"}')
    assert story.results['1']['output'] == '{"key":"value"}'


def test_stories_end_line_output_as_sting(patch, story):
    patch.object(time, 'time')
    story.results = {'1': {'start': 'start'}}
    story.end_line('1', output='   foobar\n\t')
    assert story.results['1']['output'] == '   foobar\n\t'


def test_stories_end_line_output_as_bytes(patch, story):
    patch.object(time, 'time')
    story.results = {'1': {'start': 'start'}}
    story.end_line('1', output=b'output')
    assert story.results['1']['output'] == b'output'


@mark.parametrize('input,output', [
    (None, 'null'),
    (False, 'false'),
    (True, 'true'),
    ('string', "'string'"),
    ("st'ring", "'st\'ring'"),
    (1, "'1'"),
    ({'foo': 'bar'}, "'{\"foo\": \"bar\"}'"),
    (['foobar'], "'[\"foobar\"]'"),
])
def test_stories_encode(story, input, output):
    assert story.encode(input) == output


def test_stories_argument_by_name_empty(story):
    assert story.argument_by_name({}, 'foo') is None


def test_stories_argument_by_name_lookup(patch, story):
    line = {
        'args': [
            {
                '$OBJECT': 'argument',
                'name': 'foo',
                'argument': {'$OBJECT': 'string', 'string': 'bar'}
            }
        ]
    }

    patch.object(story, 'resolve')
    story.argument_by_name(line, 'foo')
    story.resolve.assert_called_with(line['args'][0]['argument'], encode=False)


def test_stories_argument_by_name_missing(patch, story):
    line = {'args': []}
    assert story.argument_by_name(line, 'foo') is None


def test_stories_prepare(story):
    story.prepare(None)


def test_stories_prepare_context(story, app):
    story.app = app
    context = {'app': app.app_context}
    story.prepare(context=context)
    assert story.environment == app.environment
    assert story.context == context


def test_stories_next_block_simple(patch, story):
    story.tree = {
        '2': {'ln': '2', 'enter': '3', 'next': '3'},
        '3': {'ln': '3', 'parent': '2', 'next': '4'},
        '4': {'ln': '4'}
    }

    assert isinstance(story, Stories)

    assert story.next_block(story.line('2')) == story.tree['4']


def test_stories_next_block_as_lines(patch, story):
    story.tree = {
        '2': {'ln': '2', 'next': '3'},
        '3': {'ln': '3', 'next': '4'}
    }

    assert isinstance(story, Stories)

    assert story.next_block(story.line('2')) == story.tree['3']


def test_stories_next_block_where_next_block_is_block(patch, story):
    story.tree = {
        '2': {'ln': '2', 'next': '3'},
        '3': {'ln': '3', 'next': '4', 'enter': '4'},
        '4': {'ln': '4', 'parent': '3'}
    }

    assert isinstance(story, Stories)

    assert story.next_block(story.line('2')) == story.tree['3']


def test_stories_next_block_only_block(patch, story):
    story.tree = {
        '2': {'ln': '2'}
    }

    assert isinstance(story, Stories)

    assert story.next_block(story.line('2')) is None


def test_stories_context_for_function_call(story):
    assert story.context_for_function_call({}, {}) == {}


def test_stories_context_for_function_call_with_args(story):
    line = {
        'args': [
            {
                '$OBJECT': 'argument',
                'name': 'foo',
                'argument': {
                    '$OBJECT': 'string',
                    'string': 'bar'
                }
            },
            {
                '$OBJECT': 'argument',
                'name': 'foo1',
                'argument': {
                    '$OBJECT': 'string',
                    'string': 'bar1'
                }
            }
        ]
    }

    function_line = {
        'args': [
            {
                '$OBJECT': 'argument',
                'name': 'foo',
                'argument': {
                    '$OBJECT': 'type',
                    'type': 'string'
                }
            },
            {
                '$OBJECT': 'argument',
                'name': 'foo1',
                'argument': {
                    '$OBJECT': 'type',
                    'type': 'string'
                }
            }
        ]
    }

    assert story.context_for_function_call(line, function_line) == {
        'foo': 'bar',
        'foo1': 'bar1'
    }


def test_stories_next_block_nested(patch, story):
    story.tree = {
        '2': {'ln': '2', 'enter': '3', 'next': '3'},
        '3': {'ln': '3', 'parent': '2', 'next': '4'},
        '4': {'ln': '4', 'enter': '5', 'parent': '2', 'next': '5'},
        '5': {'ln': '5', 'parent': '4', 'next': '6'},
        '6': {'ln': '6', 'parent': '4', 'next': '7'},
        '7': {'ln': '7'}
    }

    assert isinstance(story, Stories)

    assert story.next_block(story.line('2')) == story.tree['7']


def test_stories_next_block_last_line(patch, story):
    story.tree = {
        '2': {'ln': '2', 'enter': '3', 'next': '3'},
        '3': {'ln': '3', 'parent': '2', 'next': '4'},
        '4': {'ln': '4', 'enter': '5', 'parent': '2', 'next': '5'},
        '5': {'ln': '5', 'parent': '4', 'next': '6'},
        '6': {'ln': '6', 'parent': '4'}
    }

    assert isinstance(story, Stories)

    assert story.next_block(story.line('2')) is None


def test_stories_next_block_nested_inner(patch, story):
    story.tree = {
        '2': {'ln': '2', 'enter': '3', 'next': '3'},
        '3': {'ln': '3', 'parent': '2', 'next': '4'},
        '4': {'ln': '4', 'enter': '5', 'parent': '2', 'next': '5'},
        '5': {'ln': '5', 'parent': '4', 'next': '6'},
        '6': {'ln': '6', 'parent': '4', 'next': '7'},
        '7': {'ln': '7', 'parent': '2', 'next': '8'},
        '8': {'ln': '8', 'parent': '2'}
    }

    assert isinstance(story, Stories)

    assert story.tree['7'] == story.next_block(story.line('4'))
