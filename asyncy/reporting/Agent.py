import os
import re


class ReportingAgent:

    @staticmethod
    def cleanup_traceback(traceback_str: str):
        cwd = os.path.normpath(os.getcwd())
        return re.sub(cwd, '', traceback_str)

    async def publish_exc(self, exc_info: BaseException, exc_data: dict, agent_options=None):
        return
