# -*- coding: utf-8 -*-
import os
import socket


class Config:

    defaults = {
        'ASYNCY_HTTP_GW_HOST': 'gateway',
        'ASYNCY_SYNAPSE_HOST': 'synapse',
        'ASYNCY_SYNAPSE_PORT': 80,
        'LOGGER_NAME': 'storyscript',
        'LOGGER_LEVEL': 'debug',
        'INGRESS_GLOBAL_STATIC_IP_NAME': 'storyscript-and-storyscriptapp',
        'APP_DOMAIN': 'storyscriptapp.com',
        'POSTGRES': 'options='
                    '--search_path=app_public,app_hidden,app_private,public '
                    'dbname=postgres user=postgres',
        'ENGINE_HOST': socket.gethostname(),
        'CLUSTER_CERT': '',
        'CLUSTER_AUTH_TOKEN': '',
        'CLUSTER_HOST': 'kubernetes.default.svc',
        'REPORTING_SENTRY_DSN': None,
        'REPORTING_SLACK_WEBHOOK': None,
        'REPORTING_CLEVERTAP_ACCOUNT': None,
        'REPORTING_CLEVERTAP_PASS': None
    }

    ENGINE_PORT = None

    def __init__(self):
        self.apply()

    def apply(self):
        """
        Applies values, taking them from the environment or from the defaults
        """
        for key, value in self.defaults.items():
            setattr(self, key, os.getenv(key, default=value))

    def __getattribute__(self, name):
        """
        Gets an attribute or returns None
        """
        try:
            return object.__getattribute__(self, name)
        except AttributeError:
            return None
