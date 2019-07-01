# -*- coding: utf-8 -*-
import typing

ContainerConfig = typing.NamedTuple('ContainerConfig', [
    ('name', str),
    ('data', dict),
])

ContainerConfigs = typing.List[ContainerConfig]
