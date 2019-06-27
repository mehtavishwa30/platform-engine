# -*- coding: utf-8 -*-
import time

from requests.structures import CaseInsensitiveDict

import tornado
from tornado.httputil import HTTPServerRequest

import ujson

from .BaseHandler import BaseHandler
from .. import Metrics
from ..Apps import Apps
from ..constants import ContextConstants
from ..entities.Multipart import FileFormField
from ..processing import Story

CLOUD_EVENTS_FILE_KEY = '_ce_payload'


class StoryEventHandler(BaseHandler):

    async def run_story(self, app_id, story_name, block, event_body):
        io_loop = tornado.ioloop.IOLoop.current()
        context = {
            ContextConstants.service_event: event_body,
            ContextConstants.server_io_loop: io_loop,
            ContextConstants.server_request: self
        }

        app = Apps.get(app_id)

        for key in self.get_req().files.keys():
            if key == CLOUD_EVENTS_FILE_KEY:
                continue

            tf = self.get_req().files[key][0]
            f = FileFormField(name=key, body=tf.body,
                              filename=tf.filename,
                              content_type=tf.content_type)
            event_body.setdefault('data', {})[key] = f

        try:
            await Story.run(app, app.logger,
                            story_name=story_name,
                            context=context,
                            block=block)
            return True
        except BaseException as e:
            app.logger.error('Failed to execute story', e)
            return False

    async def post(self):
        start = time.time()
        story_name = self.get_argument('story')
        block = self.get_argument('block')
        app_id = self.get_argument('app')

        try:
            event_body = self.get_ce_event_payload()
            self.logger.info(f'Running story for {app_id}: '
                             f'{story_name} @ {block} for '
                             f'event {event_body}')
            success = await self.run_story(app_id, story_name, block,
                                           event_body)

            if not success:
                self.set_status(500)
                self.finish()

            if not self.is_finished():
                self.set_status(200)
                self.finish()
        except BaseException as e:
            self.handle_story_exc(app_id, story_name, e)
        finally:
            Metrics.story_request.labels(
                app_id=app_id,
                story_name=story_name
            ).observe(time.time() - start)

    def get_req(self) -> HTTPServerRequest:
        """
        Wrapper method only to provide type hint to the IDE.
        """
        return self.request

    def get_ce_event_payload(self) -> dict:
        ct = self.get_req().headers.get('Content-Type')
        assert isinstance(ct, str)

        payload: dict
        if ct.startswith('application/json'):
            payload = ujson.loads(self.request.body)
        elif ct.startswith('multipart/form-data'):
            file = self.get_req().files.get(CLOUD_EVENTS_FILE_KEY)
            assert file is not None  # If not there, then we need to raise.
            assert len(file) == 1  # There can be only one payload.
            assert file[0].content_type == 'application/json'
            payload = ujson.loads(file[0].body.decode('utf-8'))
        else:
            raise Exception(f'Unsupported Content-Type ({ct}) '
                            f'for CloudEvents payload!')

        if payload.get('eventType') == 'http_request' \
                and payload.get('source') == 'gateway':
            headers = payload.get('data', {}).get('headers', None)
            if headers is not None:
                headers = CaseInsensitiveDict(data=headers)
                payload['data']['headers'] = headers

        return payload
