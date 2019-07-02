# -*- coding: utf-8 -*-
from ..Exceptions import StoryscriptRuntimeError


class OmgError(StoryscriptRuntimeError):
    pass


class UnsupportedTypeOmgError(OmgError):

    def __init__(self, type_name):
        super().__init__(f'The type "{type_name}" '
                         'is not supported by the OMG specification')


class MissingFieldOmgError(OmgError):
    """
    Raised when response body does not contain
    the key from microservice.yml
    """
    def __init__(self, key, action_resolution_chain, body):
        service_name = action_resolution_chain[0].name
        action_name = action_resolution_chain[-1].name
        super().__init__(
            f'The field "{key}" declared in the output of '
            f'{service_name}/{action_name} was not found! '
            f'Please report this to the Storyscript team.'
            f'Output received: {body}')


class FieldValueTypeMismatchOmgError(OmgError):
    """
    Raised when the property type from microservice.yml does not match
    the value type in the response body.
    """
    def __init__(self, key, expected_type, actual_type, value,
                 action_resolution_chain):
        service_name = action_resolution_chain[0].name
        action_name = action_resolution_chain[-1].name
        super().__init__(
            f'The field "{key}" declared in the output of '
            f'{service_name}/{action_name} does not match the type declared! '
            f'Expected {expected_type}, but received {actual_type}.'
            f'Please report this to the Storyscript team.'
            f'Value received: {value}')
