# -*- coding: utf-8 -*-
import typing


Release = typing.NamedTuple('Release', [
    ('app_uuid', str),
    ('version', int),
    ('environment', dict),
    ('stories', typing.Union[dict, None]),
    ('maintenance', bool),
    ('app_dns', str),
    ('state', str),
    ('deleted', bool),
    ('owner_uuid', str),
])
