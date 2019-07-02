# -*- coding: utf-8 -*-
from collections import deque

from asyncy.Types import Command, Service
from asyncy.omg.Exceptions import FieldValueTypeMismatchOmgError,\
    MissingFieldOmgError, UnsupportedTypeOmgError
from asyncy.omg.ServiceOutputValidator import ServiceOutputValidator

import pytest
from pytest import fixture, mark


@fixture
def simple_chain():
    chain = deque()
    chain.append(Service(name='service_name'))
    chain.append(Command(name='action_name'))
    return chain


@mark.parametrize('omg_type,actual_value,expect_throw', [
    ('string', 'hello world', False),
    ('string', 0.1, True),
    ('string', 10, True),
    ('string', True, True),
    ('string', None, False),
    ('int', 10, False),
    ('int', 10.1, True),
    # ('int', True, True), Will fail because of bool being a subclass of int
    ('int', 'a', True),
    ('int', None, False),
    ('float', 0.1, False),
    ('float', 1, True),
    ('float', True, True),
    ('float', '', True),
    ('float', None, False),
    ('number', 10, False),
    ('number', 10.0, False),
    ('number', 10.5, False),
    # ('number', True, True), Will fail because of bool being a subclass of int
    ('number', '10', True),
    ('number', None, False),
    ('boolean', True, False),
    ('boolean', False, False),
    ('boolean', 10, True),
    ('boolean', 1, True),
    ('boolean', 0, True),
    ('boolean', None, False),
    ('map', {}, False),
    ('map', 0, True),
    ('map', 'hello world', True),
    ('map', None, False),
    ('list', [], False),
    ('list', [1, 2], False),
    ('list', ['1', '2'], False),
    ('list', 1, True),
    ('list', None, False),
    ('any', 1, False),
    ('any', '', False),
    ('any', '19', False),
    ('any', 0.5, False),
    ('any', [], False),
    ('any', {}, False),
    ('any', True, False),
    ('any', False, False),
    ('any', None, False),
])
def test_raise_if_invalid(actual_value, omg_type, expect_throw, simple_chain):
    command_conf = {
        'type': 'object',
        'contentType': 'application/json',
        'properties': {
            'value': {
                'type': omg_type
            }
        }
    }

    output = {
        'value': actual_value
    }

    if expect_throw:
        with pytest.raises(FieldValueTypeMismatchOmgError):
            ServiceOutputValidator.raise_if_invalid(
                command_conf, output, simple_chain)
    else:
        ServiceOutputValidator.raise_if_invalid(
            command_conf, output, simple_chain)


def test_raise_for_type_mismatch_unsupported_omg():
    with pytest.raises(UnsupportedTypeOmgError):
        ServiceOutputValidator.raise_for_type_mismatch(
            'foo', 'unknown_omg_type', 0, None)


def test_raise_if_invalid_for_missing_key(simple_chain):
    command_conf = {
        'type': 'object',
        'contentType': 'application/json',
        'properties': {
            'my_field': {
                'type': 'int'
            }
        }
    }

    output = {}

    with pytest.raises(MissingFieldOmgError):
        ServiceOutputValidator.raise_if_invalid(
            command_conf, output, simple_chain)


def test_raise_if_invalid_for_null_object(simple_chain):
    command_conf = {
        'type': 'object',
        'contentType': 'application/json',
        'properties': {
            'my_object': {
                'type': 'object'
            }
        }
    }

    output = {'my_object': None}

    with pytest.raises(MissingFieldOmgError):
        ServiceOutputValidator.raise_if_invalid(
            command_conf, output, simple_chain)


@mark.parametrize('error_out_deep', [True, False])
def test_raise_if_invalid_nested(simple_chain, error_out_deep):
    command_conf = {
        'type': 'object',
        'contentType': 'application/json',
        'properties': {
            'd0': {
                'type': 'object',
                'properties': {
                    'd1': {
                        'type': 'object',
                        'properties': {
                            'd2': {
                                'type': 'int'
                            }
                        }
                    }
                }
            }
        }
    }

    output = {'d0': {'d1': {'d2': 'not_int' if error_out_deep else 100}}}
    if error_out_deep:
        with pytest.raises(FieldValueTypeMismatchOmgError):
            ServiceOutputValidator.raise_if_invalid(
                command_conf, output, simple_chain)
    else:
        ServiceOutputValidator.raise_if_invalid(
            command_conf, output, simple_chain)
