from statistics import mean
from typing import Dict, List, Union

import psycopg2
from psycopg2.extras import RealDictCursor

from .Config import Config
from .entities.ContainerConfig import ContainerConfig, ContainerConfigs
from .entities.Release import Release
from .enums.ReleaseState import ReleaseState


class Database:

    METRICS_SIZE = 25

    @classmethod
    def new_pg_conn(cls, config: Config):
        conn = psycopg2.connect(config.POSTGRES)
        return conn

    @classmethod
    def get_all_app_uuids_for_deployment(cls, config: Config) -> List[Dict]:
        conn = cls.new_pg_conn(config)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        query = 'select app_uuid uuid from releases group by app_uuid;'
        cur.execute(query)

        return cur.fetchall()

    @classmethod
    def update_release_state(cls, glogger, config, app_id, version,
                             state: ReleaseState):
        conn = cls.new_pg_conn(config)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        query = 'update releases ' \
                'set state = %s ' \
                'where app_uuid = %s and id = %s;'
        cur.execute(query, (state.value, app_id, version))

        conn.commit()
        cur.close()
        conn.close()

        glogger.info(f'Updated state for {app_id}@{version} to {state.name}')

    @classmethod
    def get_container_configs(cls, app, registry_url) -> ContainerConfigs:
        conn = cls.new_pg_conn(app.config)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        query = """
        with containerconfigs as (select name, owner_uuid, containerconfig,
                                         json_object_keys(
                                             (containerconfig->>'auths')::json
                                         ) registry
                                  from app_public.owner_containerconfigs)
        select name, containerconfig
        from containerconfigs
        where owner_uuid = %s and registry = %s
        """
        cur.execute(query, (app.owner_uuid, registry_url))
        data = cur.fetchall()
        result = []
        for config in data:
            result.append(ContainerConfig(name=config['name'],
                                          data=config['containerconfig']))
        return result

    @classmethod
    def get_release_for_deployment(cls, config, app_id) -> Release:
        conn = cls.new_pg_conn(config)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        query = """
        with latest as (select app_uuid, max(id) as id
                        from releases
                        where state != 'NO_DEPLOY'::release_state
                        group by app_uuid)
        select app_uuid, id as version, config environment, payload stories,
               maintenance, hostname app_dns, state, deleted, apps.owner_uuid
        from latest
               inner join releases using (app_uuid, id)
               inner join apps on (latest.app_uuid = apps.uuid)
               inner join app_dns using (app_uuid)
        where app_uuid = %s;
        """
        cur.execute(query, (app_id,))
        data = cur.fetchone()
        return Release(app_uuid=data['app_uuid'], version=data['version'],
                       environment=data['environment'],
                       stories=data['stories'],
                       maintenance=data['maintenance'],
                       app_dns=data['app_dns'],
                       state=data['state'], deleted=data['deleted'],
                       owner_uuid=data['owner_uuid'])

    @classmethod
    def get_all_services(cls, config: Config) -> List[Dict]:
        conn = cls.new_pg_conn(config)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        query = """
        select owners.username, services.uuid, services.name, services.alias
        from services
        join owners on owner_uuid = owners.uuid;
        """
        cur.execute(query)
        return cur.fetchall()

    @classmethod
    def get_service_usage(cls, config: Config,
                          service: dict) -> Dict[str, List[float]]:
        """
        Returns { cpu_units: [...], memory_bytes: [...] }
        """
        conn = cls.new_pg_conn(config)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        query = """
        select cpu_units, memory_bytes
        from service_usage
        where service_uuid = %s;
        """
        cur.execute(query, (service['uuid'],))
        res = cur.fetchone()
        if res is None:
            query = """
            insert into service_usage
            (service_uuid) values (%s)
            returning cpu_units, memory_bytes;
            """
            cur.execute(query, (service['uuid'],))
            conn.commit()
            res = cur.fetchone()
        return res

    @classmethod
    def update_service_usage(cls, config: Config, service: dict,
                             data: Dict[str, List[float]]):

        # Store only the last ${METRICS_SIZE} metrics
        data.update((k, v[-cls.METRICS_SIZE:]) for k, v in data.items())

        conn = cls.new_pg_conn(config)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        query = """
        update service_usage
        set cpu_units = %s, memory_bytes = %s
        where service_uuid = %s;
        """
        cur.execute(query, (data['cpu_units'], data['memory_bytes'],
                            service['uuid']))
        conn.commit()

    @classmethod
    def get_service_by_alias(cls, config: Config, service_alias) -> Dict:
        conn = cls.new_pg_conn(config)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        query = """
        select uuid from services where alias = %s
        """
        cur.execute(query, (service_alias,))
        return cur.fetchone()

    @classmethod
    def get_service_by_slug(cls, config: Config,
                            owner_username: str, service_name: str) -> Dict:
        conn = cls.new_pg_conn(config)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        query = """
        select services.uuid from services
        join owners on owner_uuid = owners.uuid
        where owners.username = %s and services.name = %s
        """
        cur.execute(query, (owner_username, service_name))
        return cur.fetchone()

    @classmethod
    def get_service_limits(cls, config: Config,
                           service: str) -> Dict[str, Union[str, float]]:
        if '/' in service:
            owner_username, service_name = service.split('/')
            service = cls.get_service_by_slug(config,
                                              owner_username, service_name)
        else:
            service = cls.get_service_by_alias(config, service)
        conn = cls.new_pg_conn(config)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        query = """
        select cpu_units, memory_bytes
        from service_usage
        where service_uuid = %s
        """
        cur.execute(query, (service['uuid'],))
        res = cur.fetchone()
        if res is None or len(res['cpu_units']) < cls.METRICS_SIZE:
            limits = {
                'cpu': '0',
                'memory': '200Mi'
            }
        else:
            limits = {
                'cpu': 1.25 * mean(res['cpu_units']),
                'memory': 1.25 * mean(res['memory_bytes'])
            }
        return limits
