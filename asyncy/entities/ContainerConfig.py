# -*- coding: utf-8 -*-
import typing

ContainerConfig = typing.NamedTuple('ContainerConfig', [
    ('name', bool),
    ('data', dict),
])

ContainerConfigs = typing.List[ContainerConfig]
