# -*- coding: utf-8 -*-
from unittest.mock import MagicMock

from asyncy.Exceptions import StoryscriptError
from asyncy.processing.Services import Services
from asyncy.processing.internal import Http
from asyncy.utils.HttpUtils import HttpUtils

import certifi

import pytest
from pytest import fixture, mark

from tornado.httpclient import AsyncHTTPClient


@fixture
def service_patch(patch):
    patch.object(Services, 'register_internal')


@fixture
def line():
    return {}


@mark.parametrize('method', [['post', 200], ['get', 201],
                             ['post', 500], ['get', 500]])
@mark.parametrize('json_response', [True, False])
@mark.parametrize('user_agent', [None, 'super_cool_agent'])
@mark.parametrize('body', [True, False])
@mark.parametrize('json_request', [True, False])
@mark.asyncio
async def test_service_http_fetch(patch, story, line, json_response,
                                  user_agent, body, json_request,
                                  service_patch, async_mock, method):
    fetch_mock = MagicMock()
    patch.object(HttpUtils, 'fetch_with_retry',
                 new=async_mock(return_value=fetch_mock))
    patch.object(AsyncHTTPClient, '__init__', return_value=None)
    patch.object(certifi, 'where', return_value='ca_certs.pem')
    resolved_args = {
        'url': 'https://asyncy.com',
        'headers': {
            'Content-Type': 'application/json'
        },
        'method': method[0],
        'body': {'foo': 'bar'}
    }

    if not json_request:
        resolved_args['body'] = '{"foo": "bar"}'

    if user_agent is not None:
        resolved_args['headers']['User-Agent'] = user_agent

    client_kwargs = {
        'method': method[0].upper(),
        'ca_certs': 'ca_certs.pem',
        'headers': {
            'Content-Type': 'application/json',
            'User-Agent': resolved_args['headers'].get('User-Agent',
                                                       'Asyncy/1.0-beta')
        },
        'body': '{"foo": "bar"}'
    }

    if not body:
        client_kwargs.pop('body')
        resolved_args.pop('body')

    fetch_mock.code = method[1]
    if json_response:
        fetch_mock.body = '{"hello": "world"}'.encode('utf-8')
        fetch_mock.headers = {'Content-Type': 'application/json'}
    else:
        fetch_mock.body = 'hello world!'.encode('utf-8')

    if round(method[1] / 100) != 2:
        with pytest.raises(StoryscriptError):
            await Http.http_post(story, line, resolved_args)
    else:
        result = await Http.http_post(story, line, resolved_args)
        HttpUtils.fetch_with_retry.mock.assert_called_with(
            3, story.logger, resolved_args['url'],
            AsyncHTTPClient(), client_kwargs
        )
        if json_response:
            assert result == {'hello': 'world'}
        else:
            assert result == fetch_mock.body.decode('utf-8')


def test_service_http_init():
    Http.init()
