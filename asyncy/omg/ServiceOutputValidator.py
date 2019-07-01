# -*- coding: utf-8 -*-
from collections import deque

from .Exceptions import FieldValueTypeMismatchOmgError, MissingFieldOmgError, \
    UnsupportedTypeOmgError


class ServiceOutputValidator:
    """
    Class to verify the output of a service.
    """

    omg_types_to_python_types: [str, type] = {
        'string': str,
        'int': int,
        'boolean': bool,
        'map': dict,
        'float': float,
        'list': list,
        'number': [int, float],
        'any': object
    }

    python_types_to_omg_types: [type, str] = {
        str: 'string',
        int: 'int',
        bool: 'boolean',
        dict: 'map',
        float: 'float',
        list: 'list'
    }

    @classmethod
    def raise_for_type_mismatch(cls, prop_name, omg_type_name, value,
                                action_resolution_chain):
        """
        Ensures that the value matches the expected type as listed on
        https://microservice.guide/schema/actions/#arguments.

        Supported types: int, float, number, string, list, map, boolean, or any
        """
        python_type = cls.omg_types_to_python_types.get(omg_type_name)

        if python_type is None:
            raise UnsupportedTypeOmgError(omg_type_name)

        if value is None:
            return

        cls.ensure_type(prop_name, python_type, omg_type_name,
                        value, action_resolution_chain)

    @classmethod
    def raise_if_invalid(cls, expected_output: dict, body: dict,
                         action_resolution_chain: deque):
        """
        Verify all properties are contained in the return body.

        expected_output takes the following structure:
        output:
          type: object
          contentType: application/json
          properties:
            customerId:
              type: int
            customerName:
              type: string
            bank:
              type: object  # can be nested to N levels.
              properties:
                name:
                  type: string
        """
        props = expected_output.get('properties')

        for prop_name, prop_config in props.items():
            if prop_name not in body:
                raise MissingFieldOmgError(prop_name, action_resolution_chain,
                                           body)
            elif prop_config.get('type') == 'object':
                if body.get(prop_name) is None:
                    raise MissingFieldOmgError(
                        prop_name, action_resolution_chain, body)

                cls.raise_if_invalid(prop_config, body.get(
                    prop_name), action_resolution_chain)
            else:
                cls.raise_for_type_mismatch(
                    prop_name, prop_config.get('type'),
                    body.get(prop_name), action_resolution_chain)

    @classmethod
    def ensure_type(cls, key, python_type, omg_type, val,
                    action_resolution_chain):
        """
        Check if value belongs to the type specified.
        """
        # Works because isinstance(list, list) is false.
        if isinstance(python_type, list):  # For number (it can be int/float).
            for item in python_type:
                if isinstance(val, item):
                    return
        else:
            if isinstance(val, python_type):
                return

        omg_type_name = cls.python_types_to_omg_types.get(type(val), 'unknown')

        raise FieldValueTypeMismatchOmgError(key, omg_type, omg_type_name, val,
                                             action_resolution_chain)
