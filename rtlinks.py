import re
from typing import List, Tuple, Type, Set
from mautrix.types import UserID
from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper
from maubot import Plugin, MessageEvent
from maubot.handlers import command


class Config(BaseProxyConfig):
    def do_update(self, helper: ConfigUpdateHelper) -> None:
        helper.copy("prefix")
        helper.copy("url")
        helper.copy("user")
        helper.copy("pass")
        helper.copy("whitelist")


class RTLinksPlugin(Plugin):
    prefix: str
    whitelist: Set[UserID]
    regex = re.compile(r'([a-zA-z]+): (.+)')

    async def start(self) -> None:
        #await super().start()
        self.on_external_config_update()

    def on_external_config_update(self) -> None:
        self.config.load_and_update()
        self.prefix = self.config["prefix"]
        self.whitelist = set(self.config["whitelist"])

    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        return Config

    async def can_manage(self, evt: MessageEvent) -> bool:
        if evt.sender in self.whitelist:
            return True
        return False

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
            markdown = "[rt#{}]({}) ({}) is **{}** in **{}** from {}".format(
                number,
                link,
                ticket['Subject'],
                ticket['Status'],
                ticket['Queue'],
                ticket['Creator']
            )
            msg_lines.append(markdown)

        if msg_lines:
            await evt.respond("\n".join(msg_lines))

    @command.new(name=lambda self: self.prefix,
                 help="Manage RT tickets", require_subcommand=True)
    async def rt(self) -> None:
        pass

    @rt.subcommand("resolve", help="Mark the ticket as resolved.")
    @command.argument("number", "ticket number", pass_raw=True)
    async def resolve(self, evt: MessageEvent, number: str) -> None:
        if not await self.can_manage(evt):
            return
        await evt.mark_read()
        headers = {"User-agent": "rtlinksmaubot"}
        api = '{}/REST/1.0/'.format(self.config['url'])
        api_edit = '{}ticket/{}/edit'.format(api, number)
        data = {'user': self.config['user'], 'pass': self.config['pass'],
                'content': 'Status: resolved'}
        await self.http.post(api_edit, data=data, headers=headers)

