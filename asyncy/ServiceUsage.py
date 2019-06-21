import asyncio
import base64
import json
import urllib.parse
from typing import Dict, List, Tuple, Union

from .Config import Config
from .Exceptions import K8sError
from .Kubernetes import Kubernetes
from .Logger import Logger
from .db.Database import Database


class ServiceUsage:

    WAIT_PERIOD = 5 * 60

    @classmethod
    def get_service_labels(cls, service) -> List[str]:
        """
        A service in the DB can be identified by either of:
        - owner_username / service_name
        - service_alias
        """
        slug = f"{service['username']}/{service['name']}"
        alias = service['alias']
        return [
            base64.b16encode(label.encode()).decode()
            for label in [slug, alias]
        ]

    @classmethod
    def split_value(cls, value: str,
                    suffix_len: int) -> Tuple[float, Union[str, None]]:
        suffix = value[-suffix_len:]
        if not suffix.isdigit():
            return float(value[:-suffix_len]), suffix
        else:
            return float(value), None

    @classmethod
    def memory_bytes(cls, value: str) -> float:
        base, suffix = cls.split_value(value, 2)
        multipliers = {
            None: 2.0**0,
            'Ki': 2.0**10,
            'Mi': 2.0**20,
            'Gi': 2.0**30,
            'Ti': 2.0**40,
            'Pi': 2.0**50,
            'Ei': 2.0**60
        }
        return base * multipliers[suffix]

    @classmethod
    def cpu_units(cls, value: str) -> float:
        base, suffix = cls.split_value(value, 1)
        multipliers = {
            None: 1e0,
            'n': 1e-9,
            'u': 1e-6,
            # FYI: "precision finer than 1m is not allowed" in cpu limit input
            'm': 1e-3,
            'k': 1e3,
            'M': 1e6,
            'G': 1e9,
            'T': 1e12,
            'P': 1e15,
            'E': 1e18
        }
        return base * multipliers[suffix]

    @classmethod
    async def get_pod_metrics(cls, service, config: Config,
                              logger: Logger) -> Dict:
        """
        Get the average CPU units and memory bytes
        consumed by all the running pods of a service
        """
        total_cpu = 0
        total_memory = 0
        average_cpu = None
        average_memory = None

        prefix = Kubernetes._get_api_path_prefix('metrics')
        labels = cls.get_service_labels(service)
        qs = urllib.parse.urlencode({
            'labelSelector': f'b16-service-name in ({",".join(labels)})'
        })
        res = await Kubernetes.make_k8s_call(config, logger,
                                             f'{prefix}/pods?{qs}')
        Kubernetes.raise_if_not_2xx(res)
        body = json.loads(res.body, encoding='utf-8')
        num_pods = len(body['items'])
        for pod in body['items']:
            # Assert 1:1 container to pod mapping
            if len(pod['containers']) > 1:
                raise K8sError(
                    message=f'Found {len(pod["containers"])} containers '
                    f'in pod {pod["metadata"]["name"]}, expected 1')
            # Convert metrics to standard units (no suffix)
            total_cpu += cls.cpu_units(pod['containers'][0]['usage']['cpu'])
            total_memory += cls.memory_bytes(
                pod['containers'][0]['usage']['memory'])

        if num_pods > 0:
            average_cpu = total_cpu / num_pods
            average_memory = total_memory / num_pods

        return {
            'average_cpu': average_cpu,
            'average_memory': average_memory,
            'num_pods': num_pods
        }

    @classmethod
    async def record_service_usage(cls, config: Config, logger: Logger):
        from .Service import Service
        while not Service.shutting_down:
            all_services = Database.get_all_services(config)
            for service in all_services:
                # Get cpu, memory average for all running pods of the service
                metrics = await cls.get_pod_metrics(service, config, logger)
                if metrics['num_pods'] == 0:
                    # No running pods found, nothing to do here
                    continue
                # Get stored metrics (past cpu, mem averages) of the service
                usage = Database.get_service_usage(config, service)
                # Add new set of entries to the usage arrays
                usage['cpu_units'].append(metrics['average_cpu'])
                usage['memory_bytes'].append(metrics['average_memory'])
                Database.update_service_usage(config, service, usage)
            await asyncio.sleep(cls.WAIT_PERIOD)

    @classmethod
    def start_recording(cls, config: Config, logger: Logger, loop):
        asyncio.run_coroutine_threadsafe(
            cls.record_service_usage(config, logger),
            loop
        )
