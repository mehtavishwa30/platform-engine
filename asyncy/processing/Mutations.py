# -*- coding: utf-8 -*-
from .mutations.DictMutations import DictMutations
from .mutations.ListMutations import ListMutations
from .mutations.NumberMutations import NumberMutations
from .mutations.StringMutations import StringMutations
from ..Exceptions import StoryscriptError


class Mutations:

    @classmethod
    def mutate(cls, mutation, value, story, line):
        operator = mutation['mutation']
        handler = None
        try:
            if isinstance(value, str):
                handler = getattr(StringMutations, operator)
            elif isinstance(value, list):
                handler = getattr(ListMutations, operator)
            elif isinstance(value, dict):
                handler = getattr(DictMutations, operator)
            elif isinstance(value, int) or isinstance(value, float):
                handler = getattr(NumberMutations, operator)
        except AttributeError:
            pass  # handler is None at this point.

        if handler is None:
            raise StoryscriptError(
                message=f'Unsupported data type {str(type(value))} '
                        f'for mutation {operator}',
                story=story, line=line)
        try:
            return handler(mutation, value, story, line, operator)
        except BaseException as e:
            raise StoryscriptError(
                message=f'Failed to apply mutation {operator}! err={str(e)}',
                story=story, line=line)
