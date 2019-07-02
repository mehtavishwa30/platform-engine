import asyncio
import base64
import json
import urllib.parse
from collections import defaultdict
from operator import truediv
from typing import Dict, List, Tuple, Union

import numpy as np

from .Config import Config
from .Exceptions import K8sError
from .Kubernetes import Kubernetes
from .Logger import Logger
from .db.Database import Database


class ServiceUsage:

    WAIT_PERIOD = 5 * 60
    BATCH_SIZE = 100

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
    async def get_pod_image_tag(cls, config, logger, pod):
        prefix = Kubernetes._get_api_path_prefix('pods')
        namespace = pod['metadata']['namespace']
        name = pod['metadata']['name']
        res = await Kubernetes.make_k8s_call(config, logger,
                                             f'{prefix}/{namespace}'
                                             f'/pods/{name}')
        Kubernetes.raise_if_not_2xx(res)
        body = json.loads(res.body, encoding='utf-8')
        return body['spec']['containers'][0]['image'].split(':')[-1]

    @classmethod
    async def get_pod_metrics(cls, service, config: Config,
                              logger: Logger) -> List[Dict[str, any]]:
        """
        Get the average CPU units and memory bytes
        consumed by all the running pods of a service,
        group by tag
        """
        cpu_units = defaultdict(list)
        memory_bytes = defaultdict(list)

        # Get metrics
        prefix = Kubernetes._get_api_path_prefix('metrics')
        labels = cls.get_service_labels(service)
        qs = urllib.parse.urlencode({
            'labelSelector': f'b16-service-name in ({",".join(labels)})'
        })
        res = await Kubernetes.make_k8s_call(config, logger,
                                             f'{prefix}/pods?{qs}')
        Kubernetes.raise_if_not_2xx(res)
        body = json.loads(res.body, encoding='utf-8')
        for pod in body['items']:
            # Assert 1:1 container to pod mapping
            if len(pod['containers']) > 1:
                raise K8sError(
                    message=f'Found {len(pod["containers"])} containers '
                    f'in pod {pod["metadata"]["name"]}, expected 1'
                )
            # Get tag of the image that this pod is running
            tag = await cls.get_pod_image_tag(config, logger, pod)
            # Convert metrics to standard units (no suffix)
            cpu_units[tag].append(cls.cpu_units(
                pod['containers'][0]['usage']['cpu']
            ))
            memory_bytes[tag].append(cls.memory_bytes(
                pod['containers'][0]['usage']['memory']
            ))

        return [
            {
                'service_uuid': service['uuid'],
                'tag': tag,
                'cpu_units': np.percentile(cpu_units[tag], 95),
                'memory_bytes': np.percentile(memory_bytes[tag], 95)
            }
            for tag in cpu_units.keys()
        ]

    @classmethod
    async def record_service_usage(cls, config: Config, logger: Logger):
        from .Service import Service
        while not Service.shutting_down:
            # Split services into batches,
            # Record metrics for all services in a given batch in parallel
            bulk_update_data = []
            all_services = Database.get_all_services(config)
            for i in range(0, len(all_services), cls.BATCH_SIZE):
                current_batch = all_services[i: i + cls.BATCH_SIZE]
                current_data = await asyncio.gather(*[
                    cls.get_pod_metrics(service, config, logger)
                    for service in current_batch
                ])
                bulk_update_data += [
                    tag_data
                    for service_data in current_data
                    for tag_data in service_data
                ]
            # Create default records for all new (service_uuid, tag) pairs
            Database.create_service_usage(config, bulk_update_data)
            Database.update_service_usage(config, bulk_update_data)
            # Sleep before updating metrics again
            await asyncio.sleep(cls.WAIT_PERIOD)

    @classmethod
    def start_recording(cls, config: Config, logger: Logger, loop):
        asyncio.run_coroutine_threadsafe(
            cls.record_service_usage(config, logger),
            loop
        )
