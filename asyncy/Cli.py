# -*- coding: utf-8 -*-
import click

import ujson

from .CeleryTasks import process_story


class Cli:

    @click.group()
    def main():
        pass

    @staticmethod
    @main.command()
    @click.argument('story')
    @click.argument('app_id')
    @click.option('--block', help='Processes the block after this line')
    @click.option('--context', help='Context data to start the story with')
    def run(app_id, story, block, context):
        if context:
            context = ujson.loads(context)
        process_story.delay(app_id, story, block=block, context=context)
