import psycopg2
from psycopg2.extras import RealDictCursor

from .Config import Config
from .enums.ReleaseState import ReleaseState


class Database:

    @classmethod
    def new_pg_conn(cls, config: Config):
        conn = psycopg2.connect(config.POSTGRES)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        return conn, cur

    @classmethod
    def get_all_app_uuids_for_deployment(cls, config: Config):
        conn, cur = cls.new_pg_conn(config)

        query = 'select app_uuid uuid from releases group by app_uuid;'
        cur.execute(query)

        return cur.fetchall()

    @classmethod
    def update_release_state(cls, glogger, config, app_id, version,
                             state: ReleaseState):
        conn, cur = cls.new_pg_conn(config)
        query = 'update releases ' \
                'set state = %s ' \
                'where app_uuid = %s and id = %s;'
        cur.execute(query, (state.value, app_id, version))

        conn.commit()
        cur.close()
        conn.close()

        glogger.info(f'Updated state for {app_id}@{version} to {state.name}')

    @classmethod
    def get_docker_configs(cls, app, registry_url):
        conn, cur = cls.new_pg_conn(app.config)
        query = f"""
        with containerconfigs as (select name, owner_uuid, containerconfig,
                                         json_object_keys(
                                             (containerconfig->>'auths')::json
                                         ) registry
                                  from app_public.owner_containerconfigs)
        select name, containerconfig dockerconfig
        from containerconfigs
        where owner_uuid='{app.owner_uuid}' and registry='{registry_url}'
        """
        cur.execute(query)
        return cur.fetchall()

    @classmethod
    def get_release_for_deployment(cls, config, app_id):
        conn, cur = cls.new_pg_conn(config)
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
        return cur.fetchone()
