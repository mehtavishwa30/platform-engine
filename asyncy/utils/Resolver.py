# -*- coding: utf-8 -*-
import re

from .TypeResolver import TypeResolver
from ..Exceptions import StoryscriptRuntimeError


class Resolver:

    @classmethod
    def values(cls, items_list, data):
        """
        Parses a list of values objects. The list may contain other objects.
        """
        return [
            Resolver.resolve(value, data)
            for value in items_list
        ]

    @classmethod
    def string(cls, string, data, values=None):
        """
        Resolves a string to itself. If values are given, the string
        is formatted against data, using the order in values.
        """
        if values:
            values = Resolver.values(values, data)
            return string.format(*values)
        return string

    @classmethod
    def path(cls, paths, data):
        """
        Resolves a path against some data, for example the path ['a', 'b']
        with data {'a': {'b': 'value'}} produces 'value'
        """
        resolved = None
        try:
            item = data[paths[0]]
            for path in paths[1:]:
                if isinstance(path, str):
                    item = item[path]

                assert isinstance(path, dict)
                object_type = path.get('$OBJECT')
                if object_type == 'range':
                    item = cls.range(path['range'], item, data)
                else:
                    resolved = Resolver.object(path, data)
                    item = item[resolved]
            return item
        except IndexError:
            raise StoryscriptRuntimeError(
                message=f'List index out of bounds: {resolved}')
        except KeyError:
            raise StoryscriptRuntimeError(
                message=f'Invalid key access: {item}')
        except TypeError:
            return None

    @classmethod
    def dictionary(cls, dictionary, data):
        result = {}
        for key, value in dictionary.items():
            result[key] = cls.resolve(value, data)
        return result

    @classmethod
    def list_object(cls, items, data):
        for item in items:
            yield cls.resolve(item, data)

    @classmethod
    def object(cls, item, data):
        if not isinstance(item, dict):
            return item
        object_type = item.get('$OBJECT')
        if object_type == 'string':
            if 'values' in item:
                return cls.string(item['string'], data, values=item['values'])
            return cls.string(item['string'], data)
        elif object_type == 'dot':
            return item['dot']
        elif object_type == 'int':
            return item['int']
        elif object_type == 'boolean':
            return item['boolean']
        elif object_type == 'float':
            return item['float']
        elif object_type == 'path':
            return cls.path(item['paths'], data)
        elif object_type == 'regexp':
            return re.compile(item['regexp'])
        elif object_type == 'value':
            return item['value']
        elif object_type == 'dict':
            return dict(cls.dict(item['items'], data))
        elif object_type == 'list':
            return list(cls.list_object(item['items'], data))
        elif object_type == 'expression' or object_type == 'assertion':
            return cls.expression(item, data)
        elif object_type == 'type_cast':
            return cls.type_cast(item, data)
        elif object_type == 'type':
            return cls.type_cast(item, data)
        return cls.dictionary(item, data)

    @classmethod
    def expression(cls, item, data):
        """
        Handles expression where item['assertion'/'expression']
        is one of the following:
        - equals
        - not_equal
        - greater
        - greater_equal
        - less
        - less_equal
        - not
        - or
        - sum
        - subtraction
        - division
        - multiplication
        - exponential
        """
        a = item.get('assertion', item.get('expression'))

        values = item['values']

        left = cls.resolve(values[0], data)

        if a == 'equals' or a == 'equal':
            right = cls.resolve(values[1], data)
            return left == right
        elif a == 'not_equal':
            right = cls.resolve(values[1], data)
            return left != right
        elif a == 'greater':
            right = cls.resolve(values[1], data)
            return left > right
        elif a == 'greater_equal':
            right = cls.resolve(values[1], data)
            return left >= right
        elif a == 'less':
            right = cls.resolve(values[1], data)
            return left < right
        elif a == 'less_equal':
            right = cls.resolve(values[1], data)
            return left <= right
        elif a == 'not':
            return not left
        elif a == 'or':
            if left is True:
                return True

            for i in range(1, len(values)):
                result = cls.resolve(values[i], data)
                if result is True:
                    return True

            return False
        elif a == 'and':
            if left is False:
                return False

            for i in range(1, len(values)):
                result = cls.resolve(values[i], data)
                if result is False:
                    return False

            return True
        elif a == 'sum':
            result = left

            assert type(left) in (int, float, str)
            # Sum supports flattened values since this only occurs when
            # a string like "{a} {b} {c}" is compiled. Everything else,
            # including arithmetic is compiled as a nested expression.
            for i in range(1, len(values)):
                r = cls.resolve(values[i], data)

                if type(r) in (int, float) and type(result) in (int, float):
                    result += r
                else:
                    result = f'{str(result)}{str(r)}'

            return result
        elif a == 'subtraction':
            right = cls.resolve(values[1], data)
            assert type(left) in (int, float)
            assert type(right) in (int, float)
            return left - right
        elif a == 'multiplication':
            right = cls.resolve(values[1], data)
            assert type(left) in (int, float, str)
            assert type(right) in (int, float, str)
            return left * right
        elif a == 'modulus':
            right = cls.resolve(values[1], data)
            assert type(left) in (int, float)
            assert type(right) in (int, float)
            return left % right
        elif a == 'division':
            right = cls.resolve(values[1], data)
            assert type(left) in (int, float, str)
            assert type(right) in (int, float, str)
            return left / right
        elif a == 'exponential':
            right = cls.resolve(values[1], data)
            assert type(left) in (int, float)
            assert type(right) in (int, float)
            return left ** right
        else:
            assert False, f'Unsupported operation: {a}'

    @classmethod
    def dict(cls, items, data):
        for k, v in items:
            k = cls.object(k, data)
            if k in (list, tuple, dict):
                # warn or raise?
                pass
            else:
                yield k, cls.object(v, data)

    @classmethod
    def list(cls, items, data):
        result = []
        for item in items:
            result.append(cls.resolve(item, data))
        return ' '.join(result)

    @classmethod
    def type_cast(cls, item, data):
        type_ = item['type']
        item = cls.object(item['value'], data)
        return TypeResolver.type_cast(item, type_, data)

    @classmethod
    def range(cls, path, item, data):
        start = 0
        end = len(item)
        if 'start' in path:
            start = cls.object(path['start'], data)
        if 'end' in path:
            end = cls.object(path['end'], data)
        return item[start:end]

    @classmethod
    def resolve(cls, item, data):
        if type(item) is dict:
            return cls.object(item, data)
        elif type(item) is list:
            return cls.list(item, data)
        return item
