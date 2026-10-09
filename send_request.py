import textwrap
import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Any

from common.llm_client import LLMClient
from common.schemas import Request as Rq

logger = logging.getLogger(__name__)

class Request:

    user_content = textwrap.dedent("""\
        Current Jellyfin Library:
        %s

        Incoming Files to Organize:
        %s
    """)
    output_format = Rq


    @classmethod
    def _send_request(cls, system_prompt: str, user_content: str):
        '''
        
        '''
        try:
            return LLMClient.send_request(
                system_prompt=system_prompt,
                user_content=user_content,
                output_format=cls.output_format,
                temperature=0
            )

        except:
            raise


    @staticmethod
    def read_sys_prompt():
        try:
            with open(Path(__file__).parent / "sys_prompt.txt", "r") as f:
                system_prompt = f.read()
            return system_prompt
        except FileNotFoundError:
            logger.exception("Prompt missing")
            raise

    @classmethod
    def fill_user_content(cls, library: dict, target: str | list[str]):
        user_content = cls.user_content % (
            json.dumps(library),
            ''.join([str(el) + '\n' for el in (target if type(target) is list else [target])])
            )
        # print('UC', user_content)
        return user_content

    @classmethod
    def process(cls, library: dict, target: str | list[str]) -> Rq:
        system_prompt = cls.read_sys_prompt()
        user_content = cls.fill_user_content(library, target)

        llm_result = cls._send_request(system_prompt, user_content)
        result = llm_result
        
        if result:
            logger.info("")
            return result
        logger.warning("")
        return []