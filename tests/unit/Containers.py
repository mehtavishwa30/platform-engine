# -*- coding: utf-8 -*-
import hashlib
from unittest.mock import MagicMock

from asyncy.AppConfig import Expose
from asyncy.Containers import Containers
from asyncy.Exceptions import ActionNotFound, ContainerSpecNotRegisteredError,\
    EnvironmentVariableNotFound, K8sError
from asyncy.Kubernetes import Kubernetes
from asyncy.constants.LineConstants import LineConstants
from asyncy.constants.ServiceConstants import ServiceConstants
from asyncy.db.Database import Database
from asyncy.entities.ContainerConfig import ContainerConfig
from asyncy.entities.Volume import Volume
from asyncy.processing import Story

import pytest
from pytest import fixture, mark


@fixture
def line():
    return MagicMock()


def test_is_service_reusable(story):
    story.app.services = {
        'alpine': {
            'configuration': {
                'actions': {
                    'echo': {
                        'run': 'foo'
                    }
                }
            }
        }
    }

    line = {
        LineConstants.service: 'alpine',
        LineConstants.command: 'echo'
    }

    assert Containers.is_service_reusable(story.app, line) is False
    story.app.services['alpine']['configuration']['actions']['echo'][
        'run'] = None

    assert Containers.is_service_reusable(story.app, line) is True


@mark.parametrize('reusable', [False, True])
@mark.parametrize('name', ['alpine', 'a!lpine', 'ALPINE', '__aLpInE'])
def test_get_container_name(patch, story, line, reusable, name):
    patch.object(Containers, 'is_service_reusable', return_value=reusable)
    story.app.app_id = 'my_app'
    story.app.version = 'v2'
    ret = Containers.get_container_name(story.app, story.name, line, name)
    if reusable:
        assert ret == f'alpine-{Containers.hash_service_name(story.app, name)}'
    else:
        h = Containers.hash_service_name_and_story_line(story.app, story.name,
                                                        line, name)
        assert ret == f'alpine-{h}'


def test_get_containerconfig_name(app):
    app.version = 'v1'
    config = ContainerConfig(name='name_with_special_!!!_characters', data={
        'auths': {
            'registry_url': {
                'auth': 'base64_string'
            }
        }
    })
    r = Containers.get_containerconfig_name(app, config.name)
    assert r == 'namewithspecialchara-95b9733c79792f385564973c20be433f6f6832e9'


@mark.asyncio
async def test_exec():
    with pytest.raises(K8sError):
        await Containers.exec(None, None, None, None, None)


@mark.asyncio
async def test_container_get_hostname(patch, story, line):
    story.app.app_id = 'my_app'
    patch.object(Containers, 'get_container_name', return_value='foo')
    ret = await Containers.get_hostname(story, line, 'foo')
    assert ret == 'foo.my_app.svc.cluster.local'


@mark.parametrize('image', [
    'postgres',
    'library/postgres',
    'docker.io/postgres',
    'docker.io/library/postgres',
    'index.docker.io/postgres',
])
def test_get_registry_url_official(image):
    ret = Containers.get_registry_url(image)
    assert ret == 'https://index.docker.io/v1/'


def test_get_registry_url_custom():
    image = 'cloud.canister.io:5000/repository/image'
    ret = Containers.get_registry_url(image)
    assert ret == 'cloud.canister.io:5000'


@mark.asyncio
async def test_clean_app(patch, async_mock):
    patch.object(Kubernetes, 'clean_namespace', new=async_mock())
    app = MagicMock()
    await Containers.clean_app(app)
    Kubernetes.clean_namespace.mock.assert_called_with(app)


@mark.asyncio
async def test_remove_volume(patch, story, line, async_mock):
    patch.object(Kubernetes, 'remove_volume', new=async_mock())
    await Containers.remove_volume(story.app, 'foo')
    Kubernetes.remove_volume.mock.assert_called_with(story.app, 'foo')


@mark.asyncio
async def test_prepare_for_deployment(patch, async_mock):
    patch.object(Kubernetes, 'clean_namespace', new=async_mock())
    story = MagicMock()
    await Containers.prepare_for_deployment(story)
    Kubernetes.clean_namespace.mock.assert_called_with(story.app)


def test_format_command(logger, app, echo_service, echo_line):
    story = Story.story(app, logger, 'echo.story')
    app.services = echo_service

    cmd = Containers.format_command(story, echo_line, 'alpine', 'echo')
    assert ['echo', '{"msg":"foo"}'] == cmd


@mark.parametrize('reusable', [True, False])
def test_hash_volume_name(patch, story, line, reusable):
    line['ln'] = '1'
    patch.object(Containers, 'is_service_reusable', return_value=reusable)
    name = 'my_volume'
    service = 'foo'
    key = name + '-' + service
    if not reusable:
        key = f'{key}-{line["ln"]}'

    expected = f'myvolume-' + hashlib.sha1(key.encode('utf-8')).hexdigest()
    assert Containers.hash_volume_name(story.app, line, service, name) == \
        expected


def test_hash_ingress_name():
    e = Expose(service='service',
               service_expose_name='expose_name',
               http_path='expose_path')
    ret = Containers.hash_ingress_name(e)
    assert ret == 'exposename-0cf994f170f9d213bb814f74baca87ea149f7536'


@mark.asyncio
async def test_expose_service(app, patch, async_mock):
    container_name = 'container_name'
    patch.object(Containers, 'get_container_name',
                 return_value=container_name)

    patch.object(Containers, 'create_and_start', new=async_mock())
    patch.object(Kubernetes, 'create_ingress', new=async_mock())

    e = Expose(service='service',
               service_expose_name='expose_name',
               http_path='expose_path')

    ingress_name = Containers.hash_ingress_name(e)
    hostname = f'{app.app_dns}--{Containers.get_simple_name(e.service)}'

    await Containers.expose_service(app, e)

    Containers.create_and_start.mock.assert_called_with(app, None, e.service,
                                                        container_name)

    Kubernetes.create_ingress.mock.assert_called_with(ingress_name, app, e,
                                                      container_name,
                                                      hostname=hostname)


def test_service_name_and_story_line(patch, story):
    patch.object(hashlib, 'sha1')
    story.name = 'story_name'
    story.app.version = 'v29'
    ret = Containers.hash_service_name_and_story_line(
        story.app, story.name, {'ln': '1'}, 'alpine')

    hashlib.sha1.assert_called_with(f'alpine-v29-{story.name}-1'
                                    .encode('utf-8'))
    assert ret == hashlib.sha1().hexdigest()


def test_service_name(patch, story):
    story.app.version = 'v2'
    patch.object(hashlib, 'sha1')
    ret = Containers.hash_service_name(story.app, 'alpine')

    hashlib.sha1.assert_called_with(f'alpine-v2'.encode('utf-8'))
    assert ret == hashlib.sha1().hexdigest()


@mark.asyncio
async def test_create_and_start_no_action(story):
    story.app.services = {'alpine': {'configuration': {}}}
    with pytest.raises(ActionNotFound):
        await Containers.create_and_start(story.app, {'command': 'foo'},
                                          'alpine', 'alpine')


@mark.parametrize('run_command', [None, ['/bin/bash', 'sleep', '10000']])
@mark.parametrize('with_volumes', [True, False])
@mark.parametrize('missing_required_var', [False, True])
@mark.asyncio
async def test_start(patch, story, async_mock,
                     missing_required_var,
                     run_command, with_volumes):
    line = {
        LineConstants.service: 'alpine',
        LineConstants.command: 'echo',
        'ln': '1'
    }

    patch.object(Kubernetes, 'create_pod', new=async_mock())

    story.app.services = {
        'alpine': {
            ServiceConstants.config: {
                'actions': {
                    'echo': {
                    }
                },
                'volumes': {
                    'db': {
                        'persist': True,
                        'target': '/db'
                    },
                    'tmp': {
                        'persist': False,
                        'target': '/tmp'
                    }
                },
                'environment': {
                    'param_1': {
                        'required': True
                    },
                    'alpine_only': {}
                }
            }
        }
    }

    if not with_volumes:
        del story.app.services['alpine'][ServiceConstants.config]['volumes']

    if run_command is not None:
        story.app.services['alpine'][ServiceConstants.config]['actions'][
            'echo'] = {'run': {'command': run_command}}

    story.app.environment = {
        'alpine': {
            'alpine_only': True,
            'param_1': 'hello_world'
        },
        'global': 'yes'
    }

    if missing_required_var:
        story.app.environment['alpine']['param_1'] = None

    patch.object(Containers, 'get_container_name',
                 return_value='asyncy-alpine')

    patch.object(Database, 'get_container_configs',
                 return_value=[])

    expected_volumes = []
    if with_volumes:
        hash_db = Containers.hash_volume_name(story.app, line, 'alpine', 'db')
        hash_tmp = Containers.hash_volume_name(story.app, line, 'alpine',
                                               'tmp')
        expected_volumes = [
            Volume(persist=True, name=hash_db, mount_path='/db'),
            Volume(persist=False, name=hash_tmp, mount_path='/tmp'),
        ]

    if missing_required_var:
        with pytest.raises(EnvironmentVariableNotFound):
            await Containers.start(story, line)
        return
    else:
        await Containers.start(story, line)

    Kubernetes.create_pod.mock.assert_called_with(
        app=story.app, service='alpine',
        image='alpine', container_name='asyncy-alpine',
        start_command=run_command or ['tail', '-f', '/dev/null'],
        shutdown_command=None,
        env={'alpine_only': True, 'param_1': 'hello_world'},
        volumes=expected_volumes,
        container_configs=[])


@mark.asyncio
async def test_init(story, patch, async_mock):
    patch.object(Kubernetes, 'create_namespace', new=async_mock())
    await Containers.init(story.app)
    Kubernetes.create_namespace.mock.assert_called_with(story.app)


def test_format_command_no_format(logger, app, echo_service, echo_line):
    story = Story.story(app, logger, 'echo.story')
    app.services = echo_service

    config = app.services['alpine'][ServiceConstants.config]
    config['actions']['echo']['format'] = None

    cmd = Containers.format_command(story, echo_line, 'alpine', 'echo')
    assert ['echo', '{"msg":"foo"}'] == cmd


def test_format_command_no_spec(logger, app, echo_line):
    story = Story.story(app, logger, 'echo.story')
    app.services = {}
    with pytest.raises(ContainerSpecNotRegisteredError):
        Containers.format_command(story, echo_line, 'alpine', 'echo')


def test_format_command_no_args(logger, app, echo_service, echo_line):
    story = Story.story(app, logger, 'echo.story')
    app.services = echo_service

    echo_service['alpine'][ServiceConstants.config]['actions']['echo'][
        'arguments'] = None

    cmd = Containers.format_command(story, echo_line, 'alpine', 'echo')
    assert ['echo'] == cmd


def test_format_command_with_format(patch, logger, app,
                                    echo_service, echo_line):
    story = Story.story(app, logger, 'echo.story')
    patch.object(story, 'argument_by_name', return_value='asyncy')
    app.services = echo_service

    config = app.services['alpine'][ServiceConstants.config]
    config['actions']['echo']['format'] = 'echo {msg}'

    cmd = Containers.format_command(story, echo_line, 'alpine', 'echo')
    assert ['echo', 'asyncy'] == cmd
