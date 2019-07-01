# -*- coding: utf-8 -*-
from tornado.web import RequestHandler

from ..Apps import Apps
from ..reporting.ExceptionReporter import ExceptionReporter


class BaseHandler(RequestHandler):
    logger = None

    # noinspection PyMethodOverriding
    def initialize(self, logger):
        self.logger = logger

    def handle_story_exc(self, app_id, story_name, e):
        # Always prefer the app logger if the app is available.
        try:
            logger = Apps.get(app_id).logger
        except BaseException:
            logger = self.logger
        logger.error(f'Story execution failed; cause={str(e)}', exc=e)
        self.set_status(500, 'Story execution failed')
        if not self.is_finished():
            self.finish()

        app = Apps.get(app_id)

        agent_options = {
            'app_uuid': app_id,
            'app_name': app.app_name,
            'app_version': app.version,
            'clever_ident': app.owner_email,
            'clever_event': 'App Request Failure',
            'allow_user_agents': True
        }

        if story_name is None:
            ExceptionReporter.capture_exc(
                exc_info=e, agent_options=agent_options)
        else:
            agent_options['story_name'] = story_name
            ExceptionReporter.capture_exc(
                exc_info=e, agent_options=agent_options)

    def is_finished(self):
        return self._finished

    def is_not_finished(self):
        return self.is_finished() is False
