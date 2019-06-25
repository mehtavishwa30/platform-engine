# -*- coding: utf-8 -*-
import os
import pathlib

from .Decorators import Decorators
from ...Exceptions import StoryscriptError


def safe_path(story, path):
    """
    safe_path resolves a path completely (../../a/../b) completely
    and returns an absolute path which can be used safely by prepending
    the story's tmp dir. This ensures that the story cannot abuse the system
    and write elsewhere, for example, stories.json.
    :param story: The story (Stories object)
    :param path: A path to be resolved
    :return: The absolute path, which can be used to read/write directly
    """
    story.create_tmp_dir()
    # Adding the leading "/" is important, otherwise the current working
    # directory will be used as the base path.
    path = f'/{path}'
    path = pathlib.Path(path).resolve()
    return f'{story.get_tmp_dir()}{os.fspath(path)}'


@Decorators.create_service(name='file', command='write', arguments={
    'path': {'type': 'string'},
    'content': {'type': 'any'}
})
async def file_write(story, line, resolved_args):
    path = safe_path(story, resolved_args['path'])
    try:
        with open(path, 'w') as f:
            f.write(resolved_args['content'])
    except IOError as e:
        raise StoryscriptError(message=f'Failed to write to file: {e}',
                               story=story, line=line)


@Decorators.create_service(name='file', command='read', arguments={
    'path': {'type': 'string'}
}, output_type='string')
async def file_read(story, line, resolved_args):
    path = safe_path(story, resolved_args['path'])
    try:
        with open(path, 'r') as f:
            return f.read()
    except IOError as e:
        raise StoryscriptError(message=f'Failed to read file: {e}',
                               story=story, line=line)


@Decorators.create_service(name='file', command='exists', arguments={
    'path': {'type': 'string'}
}, output_type='boolean')
async def file_exists(story, line, resolved_args):
    path = safe_path(story, resolved_args['path'])
    return os.path.exists(path)


def init():
    pass
