import asyncio
import base64
import json
import urllib.parse
from unittest import mock

from asyncy.Database import Database
from asyncy.Kubernetes import Kubernetes
from asyncy.Service import Service
from asyncy.ServiceUsage import ServiceUsage

import pytest
from pytest import mark


def test_get_service_labels():
    service = {
        'username': 'service_owner_username',
        'name': 'service_name',
        'alias': 'service_alias'
    }
    b16labels = ServiceUsage.get_service_labels(service)
    labels = list(map(lambda l: base64.b16decode(l).decode(), b16labels))
    assert sorted(labels) == sorted([
        'service_alias',
        'service_owner_username/service_name'
    ])


@mark.parametrize('value', [{
    'input': '1024',
    'output': (1024.0, None),
    'suffix_len': 1
}, {
    'input': '1024m',
    'output': (1024.0, 'm'),
    'suffix_len': 1
}, {
    'input': '1024Ki',
    'output': (1024, 'Ki'),
    'suffix_len': 2
}])
def test_split_value(value):
    assert ServiceUsage.split_value(value['input'],
                                    value['suffix_len']) == value['output']


@mark.parametrize('value', [{
    'input': '21Ki',
    'split': (21.0, 'Ki'),
    'output': 21504.0
}, {
    'input': '1Mi',
    'split': (1.0, 'Mi'),
    'output': 1048576.0
}, {
    'input': '1024',
    'split': (1024.0, None),
    'output': 1024.0
}])
def test_memory_bytes(patch, value):
    patch.object(ServiceUsage, 'split_value', return_value=value['split'])
    assert ServiceUsage.memory_bytes(value['input']) == value['output']
    ServiceUsage.split_value.assert_called_with(value['input'], 2)


@mark.parametrize('value', [{
    'input': '4m',
    'split': (4.0, 'm'),
    'output': 0.004
}, {
    'input': '1k',
    'split': (1.0, 'k'),
    'output': 1000
}, {
    'input': '5',
    'split': (5.0, None),
    'output': 5.0
}])
def test_cpu_units(patch, value):
    patch.object(ServiceUsage, 'split_value', return_value=value['split'])
    assert ServiceUsage.cpu_units(value['input']) == value['output']
    ServiceUsage.split_value.assert_called_with(value['input'], 1)


@mark.parametrize('value', [{
    'pod_metrics': {
        'average_cpu': None,
        'average_memory': None,
        'num_pods': 0
    },
    'usage_db': {},
    'final': {}
}, {
    'pod_metrics': {
        'average_cpu': 0.05,
        'average_memory': 12345,
        'num_pods': 3
    },
    'usage_db': {
        'cpu_units': [0.04],
        'memory_bytes': [54321]
    },
    'final': {
        'cpu_units': [0.04, 0.05],
        'memory_bytes': [54321, 12345]
    }
}])
@mark.asyncio
async def test_record_service_usage(patch, async_mock, app, value):

    Service.shutting_down = False

    def side_effect(*args, **kwargs):
        Service.shutting_down = True

    usage_db = value['usage_db']
    pod_metrics = value['pod_metrics']

    patch.object(Database, 'get_all_services',
                 return_value=[value])
    patch.object(ServiceUsage, 'get_pod_metrics',
                 new=async_mock(return_value=pod_metrics))
    patch.object(Database, 'get_service_usage',
                 return_value=usage_db)
    patch.object(Database, 'update_service_usage')

    patch.object(asyncio, 'sleep', new=async_mock(side_effect=side_effect))

    await ServiceUsage.record_service_usage(app.config, app.logger)

    if value['pod_metrics']['num_pods'] == 0:
        Database.get_service_usage.assert_not_called()
        Database.update_service_usage.assert_not_called()
    else:
        Database.get_service_usage.assert_called_with(app.config, value)
        Database.update_service_usage.assert_called_with(app.config, value,
                                                         value['final'])


@mark.parametrize('value', [{
    'k8s_response': {
        'items': []
    },
    'metrics': {
        'average_cpu': None,
        'average_memory': None,
        'num_pods': 0
    }
}, {
    'k8s_response': {
        'items': [{
            'containers': [{
                'usage': {
                    'cpu': '4m', 'memory': '21560Ki'
                }
            }]
        }, {
            'containers': [{
                'usage': {
                    'cpu': '14m', 'memory': '37040Ki'
                }
            }]
        }],
    },
    'metrics': {
        'average_cpu': pytest.approx(0.009),
        'average_memory': pytest.approx(30003200.0),
        'num_pods': 2
    }
}])
@mark.asyncio
async def test_get_pod_metrics(patch, async_mock, app, value):
    service = {
        'username': 'service_owner_username',
        'name': 'service_name',
        'alias': 'service_alias'
    }

    res = mock.MagicMock()
    res.body = json.dumps(value['k8s_response'])
    res.code = 200

    patch.object(Kubernetes, 'make_k8s_call', new=async_mock(
        return_value=res))

    ret = await ServiceUsage.get_pod_metrics(service, app.config, app.logger)

    assert ret == value['metrics']

    expected_labels = ServiceUsage.get_service_labels(service)
    expected_qs = urllib.parse.urlencode({
        'labelSelector': f'b16-service-name in ({",".join(expected_labels)})'
    })
    expected_path = Kubernetes._get_api_path_prefix('metrics') + \
        f'/pods?{expected_qs}'

    Kubernetes.make_k8s_call.mock.assert_called_with(
        app.config, app.logger, expected_path)


def test_start_recording(patch, app):
    patch.object(asyncio, 'run_coroutine_threadsafe')
    patch.object(ServiceUsage, 'record_service_usage')
    loop = mock.MagicMock()
    ServiceUsage.start_recording(app.config, app.logger, loop)
    ServiceUsage.record_service_usage.assert_called_with(app.config,
                                                         app.logger)
    asyncio.run_coroutine_threadsafe.assert_called_with(
        ServiceUsage.record_service_usage(), loop)
