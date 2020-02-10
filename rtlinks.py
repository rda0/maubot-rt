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
    headers = {"User-agent": "rtlinksmaubot"}
    regex_number = re.compile(r'[0-9]{6}')
    regex_properties = re.compile(r'([a-zA-z]+): (.+)')
    regex_history = re.compile(r'([0-9]+): (.+)')

    async def start(self) -> None:
        self.on_external_config_update()

    def on_external_config_update(self) -> None:
        self.config.load_and_update()
        self.prefix = self.config["prefix"]
        self.whitelist = set(self.config["whitelist"])
        self.api = '{}/REST/1.0/'.format(self.config['url'])
        self.post_data = {'user': self.config['user'], 'pass': self.config['pass']}

    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        return Config

    async def can_manage(self, evt: MessageEvent) -> bool:
        if evt.sender in self.whitelist:
            return True
        return False

    def is_valid_number(self, number: str) -> bool:
        if self.regex_number.match(number):
            return True
        return False

    async def get_markdown_link(self, number: str) -> str:
        link = "{}/Ticket/Display.html?id={}".format(self.config['url'], number)
        markdown = "[rt#{}]({})".format(number, link)
        return markdown

    async def _show(self, number: str) -> dict:
        await self.http.post(self.api, data=self.post_data, headers=self.headers)
        api_show = '{}ticket/{}/show'.format(self.api, number)
        async with self.http.get(api_show, headers=self.headers) as response:
            content = await response.text()
        ticket = dict(self.regex_properties.findall(content))
        return ticket

    async def _edit(self, number: str, status: str) -> None:
        api_edit = '{}ticket/{}/edit'.format(self.api, number)
        content = {'content': 'Status: {}'.format(status)}
        data = {**self.post_data, **content}
        await self.http.post(api_edit, data=data, headers=self.headers)

    async def _comment(self, number: str, comment: str) -> None:
        api_comment = '{}ticket/{}/comment'.format(self.api, number)
        content = {'content': 'id: {}\nAction: comment\nText: {}'.format(number, comment)}
        data = {**self.post_data, **content}
        await self.http.post(api_comment, data=data, headers=self.headers)

    async def _history(self, number: str) -> dict:
        await self.http.post(self.api, data=self.post_data, headers=self.headers)
        api_history = '{}ticket/{}/history'.format(self.api, number)
        async with self.http.get(api_history, headers=self.headers) as response:
            content = await response.text()
        ticket = dict(self.regex_history.findall(content))
        return ticket

    async def _entry(self, number: str, entry: str) -> dict:
        await self.http.post(self.api, data=self.post_data, headers=self.headers)
        api_entry = '{}ticket/{}/history/id/{}'.format(self.api, number, entry)
        async with self.http.get(api_entry, headers=self.headers) as response:
            content = await response.text()
        ticket = dict(self.regex_properties.findall(content))
        return ticket

    @command.passive("((^| )([rR][tT]#?))([0-9]{6})", multiple=True)
    async def handler(self, evt: MessageEvent, subs: List[Tuple[str, str]]) -> None:
        await evt.mark_read()
        msg_lines = []
        await self.http.post(self.api, data=self.post_data, headers=self.headers)
        for sub in subs:
            number = sub[4]
            api_show = '{}ticket/{}/show'.format(self.api, number)
            async with self.http.get(api_show, headers=self.headers) as response:
                content = await response.text()
            ticket = dict(self.regex_properties.findall(content))
            markdown_link = await self.get_markdown_link(number)
            markdown = "{} ({}) is **{}** in **{}** from {}".format(
                markdown_link,
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

    @rt.subcommand("show", help="Show all ticket properties.")
    @command.argument("number", "ticket number", pass_raw=True)
    async def show(self, evt: MessageEvent, number: str) -> None:
        if not await self.can_manage(evt) or not self.is_valid_number(number):
            return
        await evt.mark_read()
        properties_dict = await self._show(number)
        properties_list = ["{}: {}".format(k, v) for k, v in properties_dict.items()]
        markdown_link = await self.get_markdown_link(number)
        markdown = '{} properties:  \n{}'.format(markdown_link, '  \n'.join(properties_list))
        await evt.respond(markdown)

    @rt.subcommand("resolve", help="Mark the ticket as resolved.")
    @command.argument("number", "ticket number", pass_raw=True)
    async def resolve(self, evt: MessageEvent, number: str) -> None:
        if not await self.can_manage(evt) or not self.is_valid_number(number):
            return
        await evt.mark_read()
        await self._edit(number, 'resolved')
        markdown_link = await self.get_markdown_link(number)
        await evt.respond('{} resolved'.format(markdown_link))

    @rt.subcommand("open", help="Mark the ticket as open.")
    @command.argument("number", "ticket number", pass_raw=True)
    async def open(self, evt: MessageEvent, number: str) -> None:
        if not await self.can_manage(evt) or not self.is_valid_number(number):
            return
        await evt.mark_read()
        await self._edit(number, 'open')
        markdown_link = await self.get_markdown_link(number)
        await evt.respond('{} opened'.format(markdown_link))

    @rt.subcommand("stall", help="Mark the ticket as stalled.")
    @command.argument("number", "ticket number", pass_raw=True)
    async def stall(self, evt: MessageEvent, number: str) -> None:
        if not await self.can_manage(evt) or not self.is_valid_number(number):
            return
        await evt.mark_read()
        await self._edit(number, 'stalled')
        markdown_link = await self.get_markdown_link(number)
        await evt.respond('{} stalled'.format(markdown_link))

    @rt.subcommand("delete", help="Mark the ticket as deleted.")
    @command.argument("number", "ticket number", pass_raw=True)
    async def delete(self, evt: MessageEvent, number: str) -> None:
        if not await self.can_manage(evt) or not self.is_valid_number(number):
            return
        await evt.mark_read()
        await self._edit(number, 'deleted')
        markdown_link = await self.get_markdown_link(number)
        await evt.respond('{} deleted'.format(markdown_link))

    @rt.subcommand("autoresolve", help="Enable automatic ticket resolve mode.")
    async def autoresolve(self, evt: MessageEvent) -> None:
        if not await self.can_manage(evt):
            return
        await evt.mark_read()
        await evt.reply('😂 lol, this is your job!')

    @rt.subcommand("comment", help="Add a comment.")
    @command.argument("number", "ticket number", parser=str)
    @command.argument("comment", "comment text", pass_raw=True)
    async def comment(self, evt: MessageEvent, number: str, comment: str) -> None:
        if not await self.can_manage(evt) or not self.is_valid_number(number):
            return
        await evt.mark_read()
        await self._comment(number, comment)
        markdown_link = await self.get_markdown_link(number)
        await evt.respond('{} comment added'.format(markdown_link))

    @rt.subcommand("history", help="Get a list of all history items for a given ticket.")
    @command.argument("number", "ticket number", pass_raw=True)
    async def history(self, evt: MessageEvent, number: str) -> None:
        if not await self.can_manage(evt) or not self.is_valid_number(number):
            return
        await evt.mark_read()
        history_dict = await self._history(number)
        history_list = ["{}: {}".format(k, v) for k, v in history_dict.items()]
        markdown_link = await self.get_markdown_link(number)
        markdown = '{} history entries:  \n{}'.format(markdown_link, '  \n'.join(history_list))
        await evt.respond(markdown)

    @rt.subcommand("entry", help="Gets the history information for a single history entry.")
    @command.argument("number", "ticket number", parser=str)
    @command.argument("entry", "history entry number", parser=str)
    async def entry(self, evt: MessageEvent, number: str, entry: str) -> None:
        if not await self.can_manage(evt) or not self.is_valid_number(number):
            return
        await evt.mark_read()
        entry_dict = await self._entry(number, entry)
        entry_list = ["{}: {}".format(k, v) for k, v in entry_dict.items()]
        markdown_link = await self.get_markdown_link(number)
        markdown = '{} history entry {}:  \n{}'.format(markdown_link, entry,
                                                       '  \n'.join(entry_list))
        await evt.respond(markdown)

    @rt.subcommand("last", help="Gets the history information for the last history entry.")
    @command.argument("number", "ticket number", parser=str)
    async def last(self, evt: MessageEvent, number: str) -> None:
        if not await self.can_manage(evt) or not self.is_valid_number(number):
            return
        await evt.mark_read()
        history_dict = await self._history(number)
        entry = max(history_dict, key=int)
        entry_dict = await self._entry(number, entry)
        entry_list = ["{}: {}".format(k, v) for k, v in entry_dict.items()]
        markdown_link = await self.get_markdown_link(number)
        markdown = '{} history entry {}:  \n{}'.format(markdown_link, entry,
                                                       '  \n'.join(entry_list))
        await evt.respond(markdown)
