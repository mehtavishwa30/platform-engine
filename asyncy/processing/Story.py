# -*- coding: utf-8 -*-
import time

from .. import Metrics
from ..Exceptions import StoryscriptError
from ..Exceptions import StoryscriptRuntimeError
from ..Stories import Stories
from ..constants.ContextConstants import ContextConstants
from ..constants.LineSentinels import LineSentinels
from ..processing import Lexicon


class Story:

    @staticmethod
    def story(app, logger, story_name):
        return Stories(app, story_name, logger)

    @staticmethod
    def save(logger, story, start):
        """
        Saves the narration and the results for each line.
        """
        logger.log('story-save', story.name, story.app_id)

    @staticmethod
    async def execute(logger, story):
        """
        Executes each line in the story
        """
        line_number = story.first_line()
        while line_number:
            result = await Story.execute_line(logger, story, line_number)

            # Sentinels are not allowed to escape from here.
            if LineSentinels.is_sentinel(result):
                raise StoryscriptRuntimeError(
                    message=f'A sentinel has escaped ({result})!',
                    story=story, line=story.line(line_number))

            line_number = result
            logger.log('story-execution', line_number)

    @staticmethod
    async def execute_line(logger, story, line_number):
        """
        Executes a single line by calling the Lexicon for various operations.

        To execute a function completely, see Story#call.

        :return: Returns the next line number to be executed
        (return value from Lexicon), or None if there is none.
        """
        line: dict = story.line(line_number)
        story.start_line(line_number)

        with story.new_frame(line_number):
            try:
                method = line['method']
                if method == 'if' or method == 'else' or method == 'elif':
                    return await Lexicon.if_condition(logger, story, line)
                elif method == 'for':
                    return await Lexicon.for_loop(logger, story, line)
                elif method == 'execute':
                    return await Lexicon.execute(logger, story, line)
                elif method == 'set' or method == 'expression' \
                        or method == 'mutation':
                    return await Lexicon.set(logger, story, line)
                elif method == 'call':
                    return await Lexicon.call(logger, story, line)
                elif method == 'function':
                    return await Lexicon.function(logger, story, line)
                elif method == 'when':
                    return await Lexicon.when(logger, story, line)
                elif method == 'return':
                    return await Lexicon.ret(logger, story, line)
                elif method == 'break':
                    return await Lexicon.break_(logger, story, line)
                else:
                    raise NotImplementedError(
                        f'Unknown method to execute: {method}'
                    )
            except BaseException as e:
                # Don't wrap StoryscriptError.
                if isinstance(e, StoryscriptError):
                    e.story = story  # Always set.
                    e.line = line  # Always set.
                    raise e

                raise StoryscriptRuntimeError(message='Failed to execute line',
                                              story=story, line=line, root=e)

    @staticmethod
    async def execute_block(logger, story, parent_line: dict):
        """
        Executes all the lines whose parent is parent_line, and returns
        either one of the following:
        1. A sentinel (from LineSentinels) - if this was returned by execute()
        2. None in all other cases

        The result can have special significance, such as the BREAK
        line sentinel.
        """
        next_line = story.line(parent_line['enter'])

        # If this block represents a streaming service, copy over it's
        # output to the context, so that Lexicon can read it later.
        if parent_line.get('output') is not None \
                and parent_line.get('method') == 'when':
            story.context[ContextConstants.service_output] = \
                parent_line['output'][0]

            if story.context.get(ContextConstants.service_event) is not None:
                story.context[parent_line['output'][0]] = \
                    story.context[ContextConstants.service_event].get('data')

        while next_line is not None \
                and story.line_has_parent(parent_line['ln'], next_line):
            result = await Story.execute_line(logger, story, next_line['ln'])

            if result == LineSentinels.RETURN:
                return None  # Block has completed execution.
            elif LineSentinels.is_sentinel(result):
                return result

            next_line = story.line(result)

        return None

    @classmethod
    async def run(cls,
                  app, logger, story_name, *, story_id=None,
                  block=None, context=None,
                  function_name=None):
        start = time.time()
        try:
            logger.log('story-start', story_name, story_id)

            story = cls.story(app, logger, story_name)
            story.prepare(context)

            if function_name:
                raise StoryscriptRuntimeError('No longer supported')
            elif block:
                with story.new_frame(block):
                    await cls.execute_block(logger, story, story.line(block))
            else:
                await cls.execute(logger, story)

            logger.log('story-end', story_name, story_id)
            Metrics.story_run_success.labels(app_id=app.app_id,
                                             story_name=story_name) \
                .observe(time.time() - start)
        except BaseException as err:
            Metrics.story_run_failure.labels(app_id=app.app_id,
                                             story_name=story_name) \
                .observe(time.time() - start)
            raise err
        finally:
            Metrics.story_run_total.labels(app_id=app.app_id,
                                           story_name=story_name) \
                .observe(time.time() - start)
