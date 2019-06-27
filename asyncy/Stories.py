# -*- coding: utf-8 -*-
import pathlib
import time
import uuid
from contextlib import contextmanager
from json import dumps

from .utils import Dict
from .utils.Resolver import Resolver
from .utils.StringUtils import StringUtils

MAX_BYTES_LOGGING = 160


class Stories:

    def __init__(self, app, story_name, logger):
        self.app = app
        self.name = story_name
        self.logger = logger
        self.tree = app.stories[story_name]['tree']
        self.entrypoint = app.stories[story_name]['entrypoint']
        self.results = {}
        self.environment = None
        self.context = None
        self.containers = None
        self.repository = None
        self.version = None
        self._stack = []
        self.execution_id = str(uuid.uuid4())
        self._tmp_dir_created = False

    @contextmanager
    def new_frame(self, line_number: str):
        # No need for a try/finally block, since we don't want to unwind
        # the stack when an exception occurs.
        self._stack.append(line_number)
        yield
        self._stack.pop()

    def get_stack(self) -> []:
        return self._stack

    def create_tmp_dir(self):
        if self._tmp_dir_created:
            return

        self._tmp_dir_created = True

        path = self.get_tmp_dir()
        pathlib.Path(path).mkdir(parents=True, mode=0o700, exist_ok=True)
        self.logger.debug(f'Created tmp dir {path} (on-demand)')

    def get_tmp_dir(self):
        return f'/tmp/story.{self.execution_id}'

    def line(self, line_number):
        if line_number is None:
            return None

        return self.tree[line_number]

    def first_line(self):
        return self.entrypoint

    def line_has_parent(self, parent_line_number, line):
        """
        Looks up the hierarchy of this line to see if it
        belongs to a particular parent.

        :param parent_line_number: The parent line number
        :param line: The line to test
        :return: True if this line is a child of the parent (directly or
                 indirectly), False otherwise
        """

        # Fast test - this line is an immediate child of the parent.
        if parent_line_number == line.get('parent', None):
            return True

        while line is not None:
            my_parent_number = line.get('parent', None)

            if my_parent_number is None:
                return False

            if my_parent_number == parent_line_number:
                return True

            line = self.line(my_parent_number)

    def next_block(self, parent_line: dict):
        """
        Given a parent_line, it skips through the block and returns the next
        line after this block.
        """
        next_line = parent_line

        while next_line.get('next') is not None:
            next_line = self.line(next_line['next'])

            # See if the next line is a block. If it is, skip through it.
            if next_line.get('enter', None) is not None \
                    and next_line.get('parent') == parent_line['ln']:
                next_line = self.next_block(next_line)

                if next_line is None:
                    return None

            if not self.line_has_parent(parent_line['ln'], next_line):
                break

        # We might have skipped through all the lines in this story,
        # and ended up on on the last line.
        # If this last line belongs to the same parent, then return None.
        # This check is required because the while loop breaks when it can't
        # find a next line.
        if next_line.get('parent') is not None \
                and self.line_has_parent(parent_line['ln'], next_line):
            return None

        # If the next_line == parent_line, then there weren't any more lines
        # after the parent.
        if next_line['ln'] == parent_line['ln']:
            return None

        return next_line

    @staticmethod
    def get_str_for_logging(result) -> str:
        """
        Truncate the logged result to just N bytes.

        See https://github.com/asyncy/platform-engine/issues/188
        """
        return StringUtils.truncate(result, MAX_BYTES_LOGGING)

    def resolve(self, arg, encode=False):
        """
        Resolves line argument to their real value
        """
        if isinstance(arg, (str, int, float, bool)):
            self.logger.info(f'Resolved "{arg}" to '
                             f'"{arg}" '
                             f'with type {type(arg)}')
            return arg

        result = Resolver.resolve(arg, self.context)

        self.logger.info(f'Resolved "{arg}" to '
                         f'"{self.get_str_for_logging(result)}" '
                         f'with type {type(result)}')

        # encode and escape then format for shell
        if encode:
            return self.encode(result)
        else:
            return result

    def encode(self, arg):
        if arg is None or isinstance(arg, bool):
            return dumps(arg)
        elif isinstance(arg, (list, dict)):
            arg = dumps(arg)
        else:
            arg = str(arg)
        return "'%s'" % arg.replace("'", "\'")

    def command_arguments_list(self, arguments):
        results = []

        if arguments:
            arg = arguments[0]
            # if first path is undefined assume command
            if isinstance(arg, dict):
                if arg['$OBJECT'] == 'path' and len(arg['paths']) == 1:
                    res = self.resolve(arguments.pop(0))
                    if res is None:
                        results.append(arg['paths'][0])
                    else:
                        results.append(self.encode(res))

        if arguments:
            for argument in arguments:
                results.append(self.resolve(argument, encode=True))

        return results

    def start_line(self, line_number):
        self.results[line_number] = {'start': time.time()}

    def end_line(self, line_number, output=None, assign=None):
        start = self.results[line_number]['start']

        # Please see https://github.com/asyncy/platform-engine/issues/148
        # for the rationale on removing auto conversion. Code commented and
        # NOT removed so that this note here makes sense.
        # if isinstance(output, str):
        #     try:
        #         # try to load it as json
        #         output = loads(output)
        #     except JSONDecodeError:
        #         output = output

        dictionary = {'output': output, 'end': time.time(), 'start': start}
        self.results[line_number] = dictionary

        # assign a variable to the output
        if assign:
            self.set_variable(assign, output)

    def set_variable(self, assign, output):
        if assign is None or assign.get('paths') is None:
            self.logger.warn(
                'Output should ne assigned to something, '
                'but no variable found!')
            return

        Dict.set(self.context, assign['paths'], output)

    def function_line_by_name(self, function_name):
        """
        Returns the line at which the given function_name was defined at.
        """
        line_number = self.app.stories[self.name]['functions'][function_name]
        return self.line(line_number)

    def argument_by_name(self, line, argument_name, encode=False):
        args = line.get('args', line.get('arguments', line.get('arg')))
        if args is None:
            return None

        for arg in args:
            if (arg['$OBJECT'] == 'argument' or arg['$OBJECT'] == 'arg') and \
                    arg['name'] == argument_name:
                return self.resolve(arg.get('argument', arg.get('arg')),
                                    encode=encode)

        return None

    def context_for_function_call(self, line, function_line):
        """
        Prepares a new context for calling a function.
        This context consists of the arguments required by the function,
        and is copied over in a new map. As a result, the nature of function
        calls in Storyscript is call by value.

        Functions are executed in the following manner:
        1. Prepare a new context for the function
        2. Temporarily switch Stories#context to this new context
        3. Execute the function block
        4. Restore the original Stories#context and continue execution

        :return: A new context, which contains the arguments required (if any)
        """
        new_context = {}
        args = function_line.get('args', function_line.get('arg', []))
        for arg in args:
            if arg['$OBJECT'] == 'argument' or arg['$OBJECT'] == 'arg':
                arg_name = arg['name']
                actual = self.argument_by_name(line, arg_name)
                Dict.set(new_context, [arg_name], actual)

        return new_context

    def set_context(self, context):
        if context is None:
            context = {}
        self.context = context
        # Optimise this later.
        self.context['app'] = self.app.app_context.copy()

    def prepare(self, context=None):
        self.set_context(context)
        self.environment = self.app.environment or {}
