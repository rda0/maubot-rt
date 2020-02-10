import re
from typing import List, Tuple, Type
from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper
from maubot import Plugin, MessageEvent
from maubot.handlers import command


class Config(BaseProxyConfig):
    def do_update(self, helper: ConfigUpdateHelper) -> None:
        helper.copy("url")
        helper.copy("user")
        helper.copy("pass")


class RTLinksPlugin(Plugin):
    regex = re.compile(r'([a-zA-z]+): (.+)')

    async def start(self) -> None:
        await super().start()
        self.config.load_and_update()

    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        return Config

    @command.passive("((^| )([rR][tT]#?))([0-9]{6})", multiple=True)
    async def handler(self, evt: MessageEvent, subs: List[Tuple[str, str]]) -> None:
        await evt.mark_read()
        msg_lines = []
        headers = {"User-agent": "rtlinksmaubot"}
        api = '{}/REST/1.0/'.format(self.config['url'])
        data = {'user': self.config['user'], 'pass': self.config['pass']}
        await self.http.post(api, data=data, headers=headers)
        for sub in subs:
            number = sub[4]
            api_show = '{}ticket/{}/show'.format(api, number)
            async with self.http.get(api_show, headers=headers) as response:
                content = await response.text()
            ticket = dict(self.regex.findall(content))
            link = "{}/Ticket/Display.html?id={}".format(self.config['url'], number)
            markdown = "[rt#{}]({}) {} {} {}".format(number, link, ticket['Queue'],
                                                     ticket['Creator'], ticket['Subject'])
            msg_lines.append(markdown)

        if msg_lines:
            await evt.respond("\n".join(msg_lines))
