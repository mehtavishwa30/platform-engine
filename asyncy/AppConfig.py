# -*- coding: utf-8 -*-
import typing
from collections import namedtuple

from .utils.Dict import Dict

Expose = namedtuple('Expose',
                    ['service', 'service_expose_name', 'http_path'])

KEY_EXPOSE = 'expose'


class AppConfig:
    _expose: typing.List[Expose] = None

    def __init__(self, raw: dict):
        self._expose = []
        for expose in raw.get(KEY_EXPOSE, []):
            e = Expose(service=expose.get('service'),
                       service_expose_name=expose.get('name'),
                       http_path=Dict.find(expose, 'http.path'))

            assert e.service is not None
            assert e.service_expose_name is not None
            assert e.http_path is not None
            self._expose.append(e)

    def get_expose_config(self):
        return self._expose
