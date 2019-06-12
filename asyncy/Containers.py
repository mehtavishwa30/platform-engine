# -*- coding: utf-8 -*-
import hashlib
import re

import ujson

from .AppConfig import Expose
from .Exceptions import ActionNotFound, ContainerSpecNotRegisteredError,\
    EnvironmentVariableNotFound, K8sError
from .Kubernetes import Kubernetes
from .Types import StreamingService
from .constants.LineConstants import LineConstants
from .constants.ServiceConstants import ServiceConstants
from .entities.Volume import Volume
from .utils import Dict


class Containers:

    @classmethod
    async def remove_volume(cls, app, name):
        await Kubernetes.remove_volume(app, name)

    @classmethod
    async def prepare_for_deployment(cls, story):
        await Kubernetes.clean_namespace(story.app)

    @classmethod
    async def create_and_start(cls, app, line, service, container_name):
        """
        Creates and starts a container using the cloud provider (Kubernetes).
        :param app: The app instance
        :param line: Can be null, handled down the chain
        :param service: The name of the service
        :param container_name: The name of the container
        :return: null
        """
        # Note: 'image' is inserted by asyncy.Apps, and is not a part of the
        # OMG spec.
        omg = app.services[service][ServiceConstants.config]
        image = omg.get('image', service)

        action = None
        if line is not None:
            action = line[LineConstants.command]

        command_conf = None
        if action is not None:
            command_conf = Dict.find(omg, f'actions.{action}')

            if command_conf is None:
                raise ActionNotFound(service=service, action=action)

        shutdown_command = Dict.find(omg, f'lifecycle.shutdown.command')

        if command_conf is not None and command_conf.get('run'):
            start_command = Dict.find(command_conf, 'run.command')
        else:
            start_command = Dict.find(omg, f'lifecycle.startup.command')

        if start_command is None:
            start_command = ['tail', '-f', '/dev/null']

        volumes = []
        if omg.get('volumes'):
            for name, data in omg['volumes'].items():
                vol_name = cls.hash_volume_name(app, line, service, name)
                persist = data.get('persist', False)
                target = data.get('target', False)

                volumes.append(Volume(persist=persist, name=vol_name,
                                      mount_path=target))

        env = {}
        for key, omg_config in omg.get('environment', {}).items():
            actual_val = app.environment.get(service, {}).get(key)
            if actual_val is None:
                actual_val = omg_config.get('default')
            if omg_config.get('required', False) and actual_val is None:
                raise EnvironmentVariableNotFound(service=service,
                                                  variable=key)

            if actual_val is not None:
                env[key] = actual_val

        await Kubernetes.create_pod(app=app, service=service, image=image,
                                    container_name=container_name,
                                    start_command=start_command,
                                    shutdown_command=shutdown_command, env=env,
                                    volumes=volumes)

    @classmethod
    async def clean_app(cls, app):
        await Kubernetes.clean_namespace(app)

    @classmethod
    async def init(cls, app):
        await Kubernetes.create_namespace(app)

    @classmethod
    def is_service_reusable(cls, app, line):
        """
        A service is reusable when it doesn't need to execute a lifecycle
        command. If there's a run section in the command's config, then
        cannot be reused. Reusable commands do not have a run in their config,
        and are started via the global lifecycle config.
        """
        service = line[LineConstants.service]
        command = line[LineConstants.command]

        run = Dict.find(app.services,
                        f'{service}.configuration.actions.{command}.run')

        return run is None

    @classmethod
    async def get_hostname(cls, story, line, service_alias):
        container = cls.get_container_name(story.app, story.name, line,
                                           service_alias)
        return Kubernetes.get_hostname(story.app, container)

    @classmethod
    async def expose_service(cls, app, expose: Expose):
        container_name = cls.get_container_name(app, None, None,
                                                expose.service)
        await cls.create_and_start(app, None, expose.service, container_name)
        ingress_name = cls.hash_ingress_name(expose)
        hostname = f'{app.app_dns}--{cls.get_simple_name(expose.service)}'
        await Kubernetes.create_ingress(ingress_name, app,
                                        expose, container_name,
                                        hostname=hostname)

        app.logger.info(f'Exposed service {expose.service} as '
                        f'https://{hostname}.{app.config.APP_DOMAIN}'
                        f'{expose.http_path}')

    @classmethod
    async def start(cls, story, line):
        """
        Creates and starts a container as declared by line['service'].

        If a container already exists, then it will be reused.
        """
        service = line[LineConstants.service]
        story.logger.info(f'Starting container {service}')
        container_name = cls.get_container_name(story.app, story.name,
                                                line, service)
        await cls.create_and_start(story.app, line, service, container_name)
        hostname = await cls.get_hostname(story, line, service)

        ss = StreamingService(name=service, command=line['command'],
                              container_name=container_name,
                              hostname=hostname)

        story.logger.info(f'Started container {container_name}')
        return ss

    @classmethod
    def format_command(cls, story, line, container_name, command):
        services = story.app.services or {}
        spec = services.get(container_name)

        if spec is None:
            raise ContainerSpecNotRegisteredError(
                container_name=container_name
            )

        args = spec[ServiceConstants.config]['actions'][command]\
            .get('arguments')

        if args is None:
            return [command]

        command_format = spec[ServiceConstants.config]['actions'][command]\
            .get('format')
        if command_format is None:
            # Construct a dictionary of all arguments required and send them
            # as a JSON string to the command.
            all_args = {}
            for k in args:
                all_args[k] = story.argument_by_name(line, k)

            return [command, ujson.dumps(all_args)]

        command_parts = command_format.split(' ')

        for k in args:
            actual = story.argument_by_name(line, k)
            for i in range(0, len(command_parts)):
                command_parts[i] = command_parts[i].replace('{' + k + '}',
                                                            actual)

        return command_parts

    @classmethod
    def get_container_name(cls, app, story_name, line, name):
        """
        If a container can be reused (where reuse is defined as a command
        without a run section in it's config), it'll return a generic name
        like twitter-hash(twitter), otherwise something derived:
        twitter-hash(twitter, story name, line number).

        Why a hash? Story names can have DNS reserved characters in them,
        and hence to normalise it, we need to create a hash here.
        """
        # simple_name is included in the container name to aid debugging only.
        # It's 20 chars at max because 41 chars consists
        # of the hash and a hyphen. K8s names must be < 63 chars.
        simple_name = cls.get_simple_name(name)[:20]
        if line is None or cls.is_service_reusable(app, line):
            h = cls.hash_service_name(app, name)
        else:
            h = cls.hash_service_name_and_story_line(app, story_name,
                                                     line, name)

        return f'{simple_name}-{h}'

    @classmethod
    def hash_service_name_and_story_line(cls, app, story_name, line, name):
        return hashlib.sha1(f'{name}-{app.version}-'
                            f'{story_name}-{line["ln"]}'
                            .encode('utf-8')).hexdigest()

    @classmethod
    def get_simple_name(cls, string):
        parts = re.findall('[a-zA-Z]*', string)
        out = ''
        for i in parts:
            if i != '':
                out += i

        return out.lower()

    @classmethod
    def hash_service_name(cls, app, name):
        return hashlib.sha1(f'{name}-{app.version}'
                            .encode('utf-8')).hexdigest()

    @classmethod
    def hash_ingress_name(cls, expose: Expose):
        simple_name = cls.get_simple_name(expose.service_expose_name)[:20]
        h = hashlib.sha1(f'{expose.service}-{expose.service_expose_name}'
                         .encode('utf-8')).hexdigest()
        return f'{simple_name}-{h}'

    @classmethod
    def hash_volume_name(cls, app, line, service, volume_name):
        key = f'{volume_name}-{service}'

        if line is not None and not cls.is_service_reusable(app, line):
            key = f'{key}-{line["ln"]}'

        simple_name = cls.get_simple_name(volume_name)[:20]
        h = hashlib.sha1(key.encode('utf-8')).hexdigest()
        return f'{simple_name}-{h}'

    @classmethod
    async def exec(cls, logger, story, line, container_name, command):
        """
        Executes a command in the given container.

        Returns:
        Output of the process (stdout).

        Raises:
        asyncy.Exceptions.K8sError:
            If the execution failed for an unknown reason.
        """
        raise K8sError(story=story, line=line, message='Not implemented')
