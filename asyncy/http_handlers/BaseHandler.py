# -*- coding: utf-8 -*-
from tornado.web import RequestHandler

from ..Apps import Apps
from ..Exceptions import StoryscriptError
from ..reporting.Reporter import ExceptionReporter


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
        self.finish()
        if isinstance(e, StoryscriptError):
            ExceptionReporter.capture_exc(exc_info=e, story=e.story, line=e.line)
        else:
            if story_name is None:
                ExceptionReporter.capture_exc(exc_info=e)
            else:
                ExceptionReporter.capture_exc(exc_info=e, extra={
                    'story_name': story_name
                })

    def is_finished(self):
        return self._finished

    def is_not_finished(self):
        return self.is_finished() is False
