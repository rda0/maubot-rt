import re
from typing import List, Tuple, Type, Set, Dict
from mautrix.types import (UserID, RoomID, EventType, TextMessageEventContent, MessageType, Format,
                           ReactionEvent)
from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper
from maubot import Plugin, MessageEvent
from maubot.handlers import command


class Config(BaseProxyConfig):
    def do_update(self, helper: ConfigUpdateHelper) -> None:
        helper.copy('prefix')
        helper.copy('url')
        helper.copy('user')
        helper.copy('pass')
        helper.copy('whitelist')
        helper.copy('filter_properties')
        helper.copy('filter_entry')


class RT(Plugin):
    prefix: str
    whitelist: Set[UserID]
    api: str
    login: dict
    headers = {'User-agent': 'maubot-rt'}
    regex_ticket = re.compile(r'(?:(?:[rR][tT]#?))([0-9]+)')
    regex_number = re.compile(r'[0-9]+')
    regex_properties = re.compile(r'([a-zA-z]+): (.+)')
    regex_history = re.compile(r'([0-9]+): (.+)')
    regex_entry = re.compile(r'([a-zA-z]+): (.+(?:\n {8}.*)*)', re.MULTILINE)
    regex_assigner = re.compile(r'^.*?>(@.+:.+)<.*? assigned')
    take_this = f'(\U0001F44D this to take the ticket)'
    interesting = [
        'Ticket created',
        'Correspondence added',
        'Comments added',
    ]

    async def start(self) -> None:
        self.on_external_config_update()

    def on_external_config_update(self) -> None:
        self.config.load_and_update()
        self.prefix = self.config['prefix']
        self.whitelist = set(self.config['whitelist'])
        self.url = self.config['url']
        self.rest = f'{self.url}/REST/1.0/'
        self.display = f'{self.url}/Ticket/Display.html'
        self.login = {'user': self.config['user'], 'pass': self.config['pass']}
        self.filter_properties = set(self.config['filter_properties'])
        self.filter_entry = set(self.config['filter_entry'])

    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        return Config

    def can_manage(self, evt: MessageEvent) -> bool:
        return True if evt.sender in self.whitelist else False

    def valid_number(self, number: str) -> bool:
        return True if self.regex_number.match(number) else False

    def filter_dict(self, raw: dict, keys: Set) -> dict:
        return {k: v for k, v in raw.items() if k in keys}

    def markdown_link(self, number: str) -> str:
        return f'[rt#{number}]({self.display}?id={number})'

    def html_link(self, number: str) -> str:
        return f'<a href="{self.display}?id={number}">rt#{number}</a>'

    async def _member_mxids(self, room_id: RoomID) -> Dict[UserID, str]:
        room_members = await self.client.get_joined_members(room_id)
        member_mxids = {}
        for mxid in room_members.keys():
            displayname = await self._displayname(room_id, mxid)
            member_mxids[displayname] = mxid
        return member_mxids

    async def _displayname(self, room_id: RoomID, user_id: UserID) -> str:
        event = await self.client.get_state_event(room_id, EventType.ROOM_MEMBER, user_id)
        return event.displayname

    async def _properties(self, number: str) -> dict:
        await self.http.post(self.rest, data=self.login, headers=self.headers)
        rest = f'{self.rest}ticket/{number}/show'
        async with self.http.get(rest, headers=self.headers) as response:
            content = await response.text()
        raw = dict(self.regex_properties.findall(content))
        return self.filter_dict(raw, self.filter_properties)

    async def _edit(self, number: str, properties: dict) -> None:
        rest = f'{self.rest}ticket/{number}/edit'
        content = {'content': '\n'.join([f'{k}: {v}' for k, v in properties.items()])}
        data = {**self.login, **content}
        await self.http.post(rest, data=data, headers=self.headers)

    async def _comment(self, number: str, action: str, text: str) -> None:
        rest = f'{self.rest}ticket/{number}/comment'
        multiline_text = text.replace('\n', '\n ')
        content = {'content': f'id: {number}\nAction: {action}\nText: {multiline_text}'}
        data = {**self.login, **content}
        await self.http.post(rest, data=data, headers=self.headers)

    async def _history(self, number: str) -> dict:
        await self.http.post(self.rest, data=self.login, headers=self.headers)
        rest = f'{self.rest}ticket/{number}/history'
        async with self.http.get(rest, headers=self.headers) as response:
            content = await response.text()
        return dict(self.regex_history.findall(content))

    async def _entry(self, number: str, entry: str) -> dict:
        await self.http.post(self.rest, data=self.login, headers=self.headers)
        rest = f'{self.rest}ticket/{number}/history/id/{entry}'
        async with self.http.get(rest, headers=self.headers) as response:
            content = await response.text()
        raw = dict(self.regex_entry.findall(content))
        entry = self.filter_dict(raw, self.filter_entry)
        if 'Content' in entry and '\n' in entry['Content']:
            block = '  \n```\n' + entry['Content'].replace('\n' + ' ' * 9, '\n').rstrip() + '\n```'
            entry['Content'] = block
        return entry

    async def _search(self, params: dict) -> dict:
        rest = f'{self.rest}search/ticket'
        async with self.http.get(rest, headers=self.headers, params=params) as response:
            content = await response.text()
        return dict(self.regex_history.findall(content))

    @command.passive('((^| )([rR][tT]#?))([0-9]+)', multiple=True)
    async def handler(self, evt: MessageEvent, subs: List[Tuple[str, str]]) -> None:
        await evt.mark_read()
        msg_lines = []
        await self.http.post(self.rest, data=self.login, headers=self.headers)
        for sub in subs:
            number = sub[4]
            rest = f'{self.rest}ticket/{number}/show'
            async with self.http.get(rest, headers=self.headers) as response:
                content = await response.text()
            ticket = dict(self.regex_properties.findall(content))
            markdown = '{} is **{}** in **{}** from {}  \n{}'.format(
                self.markdown_link(number),
                ticket['Status'],
                ticket['Queue'],
                ticket['Creator'],
                ticket['Subject']
            )
            msg_lines.append(markdown)
        if msg_lines:
            if len(msg_lines) == 1:
                msg_lines += [self.take_this]
            await evt.respond('  \n'.join(msg_lines))

    @command.passive(regex=r"(?:\U0001F44D[\U0001F3FB-\U0001F3FF]?)",
                     field=lambda evt: evt.content.relates_to.key,
                     event_type=EventType.REACTION, msgtypes=None)
    async def react_took(self, evt: ReactionEvent, _: Tuple[str]) -> None:
        username = evt.sender[1:].split(':')[0]
        displayname = await self._displayname(evt.room_id, evt.sender)
        target_evt = await self.client.get_event(evt.room_id, evt.content.relates_to.event_id)
        target_ticket = self.regex_ticket.findall(target_evt.content.body)
        if len(target_ticket) == 1:
            number = target_ticket[0]
            await self._edit(number, {'Owner': username})
            content = TextMessageEventContent(
                msgtype=MessageType.NOTICE, format=Format.HTML,
                body=f'{displayname} took {number}',
                formatted_body=f'<a href="https://matrix.to/#/{evt.sender}">{evt.sender}</a> '
                f'took <code>{number}</code>')
            await self.client.send_message(evt.room_id, content)

    @command.passive(regex=r"(?:\U0001F595[\U0001F3FB-\U0001F3FF]?)",
                     field=lambda evt: evt.content.relates_to.key,
                     event_type=EventType.REACTION, msgtypes=None)
    async def react_reject(self, evt: ReactionEvent, _: Tuple[str]) -> None:
        displayname = await self._displayname(evt.room_id, evt.sender)
        target_evt = await self.client.get_event(evt.room_id, evt.content.relates_to.event_id)
        target_ticket = self.regex_ticket.findall(target_evt.content.body)
        target_mxid = self.regex_assigner.findall(target_evt.content.formatted_body)[0]
        target_username = target_mxid[1:].split(':')[0]
        target_displayname = await self._displayname(evt.room_id, target_mxid)
        if len(target_ticket) == 1:
            number = target_ticket[0]
            await self._edit(number, {'Owner': target_username})
            content = TextMessageEventContent(
                msgtype=MessageType.NOTICE, format=Format.HTML,
                body=f'{displayname} politely rejected {number} and gave it back to '
                     f'{target_displayname}',
                formatted_body=f'<a href="https://matrix.to/#/{evt.sender}">{evt.sender}</a> '
                f'politely rejected <code>{number}</code> and gave it back to '
                f'<a href="https://matrix.to/#/{target_mxid}">{target_mxid}</a>')
            await self.client.send_message(evt.room_id, content)

    @command.new(name=lambda self: self.prefix,
                 help='Manage RT tickets', require_subcommand=True)
    async def rt(self) -> None:
        pass

    @rt.subcommand('properties', aliases=('p', 'prop'), help='Show all ticket properties.')
    @command.argument('number', 'ticket number', parser=str)
    async def properties(self, evt: MessageEvent, number: str) -> None:
        if not self.can_manage(evt) or not self.valid_number(number):
            return
        await evt.mark_read()
        properties_dict = await self._properties(number)
        properties = '  \n'.join([f'{k}: {v}' for k, v in properties_dict.items()])
        await evt.respond(f'{self.markdown_link(number)} properties:  \n{properties}'
                          f'  \n{self.take_this}')

    @rt.subcommand('resolve', aliases=('r', 'res'), help='Mark the ticket as resolved.')
    @command.argument('number', 'ticket number', parser=str)
    async def resolve(self, evt: MessageEvent, number: str) -> None:
        if not self.can_manage(evt) or not self.valid_number(number):
            return
        await evt.mark_read()
        await self._edit(number, {'Status': 'resolved'})
        await evt.respond(f'{self.markdown_link(number)} resolved 😃 {self.take_this}')

    @rt.subcommand('open', aliases=('o', 'op'), help='Mark the ticket as open.')
    @command.argument('number', 'ticket number', parser=str)
    async def open(self, evt: MessageEvent, number: str) -> None:
        if not self.can_manage(evt) or not self.valid_number(number):
            return
        await evt.mark_read()
        await self._edit(number, {'Status': 'open'})
        await evt.respond(f'{self.markdown_link(number)} opened 😐️ {self.take_this}')

    @rt.subcommand('stall', aliases=('st', 'sta'), help='Mark the ticket as stalled.')
    @command.argument('number', 'ticket number', parser=str)
    async def stall(self, evt: MessageEvent, number: str) -> None:
        if not self.can_manage(evt) or not self.valid_number(number):
            return
        await evt.mark_read()
        await self._edit(number, {'Status': 'stalled'})
        await evt.respond(f'{self.markdown_link(number)} stalled 😴 {self.take_this}')

    @rt.subcommand('delete', aliases=('d', 'del'), help='Mark the ticket as deleted.')
    @command.argument('number', 'ticket number', parser=str)
    async def delete(self, evt: MessageEvent, number: str) -> None:
        if not self.can_manage(evt) or not self.valid_number(number):
            return
        await evt.mark_read()
        await self._edit(number, {'Status': 'deleted'})
        await evt.respond(f'{self.markdown_link(number)} deleted 🤬 {self.take_this}')

    @rt.subcommand('queue', aliases=('q', 'que'), help='Put the ticket in queue.')
    @command.argument('number', 'ticket number', parser=str)
    @command.argument('qid', 'queue id', parser=str)
    async def queue(self, evt: MessageEvent, number: str, qid: str) -> None:
        if not self.can_manage(evt) or not self.valid_number(number):
            return
        await evt.mark_read()
        await self._edit(number, {'Status': 'open', 'Queue': qid})
        await evt.respond(f'{self.markdown_link(number)} queued in **{qid}** 😐️ {self.take_this}')

    @rt.subcommand('comment', aliases=('c', 'com'), help='Add a comment.')
    @command.argument('number', 'ticket number', parser=str)
    @command.argument('text', 'comment text', pass_raw=True)
    async def comment(self, evt: MessageEvent, number: str, text: str) -> None:
        if not self.can_manage(evt) or not self.valid_number(number):
            return
        await evt.mark_read()
        await self._comment(number, 'comment', text)
        displayname = await self._displayname(evt.room_id, evt.sender)
        content = TextMessageEventContent(
            msgtype=MessageType.NOTICE, format=Format.HTML,
            body=f'{displayname} commented 🤓 on {number} {self.take_this}',
            formatted_body=f'<a href="https://matrix.to/#/{evt.sender}">{evt.sender}</a> '
            f'commented 🤓 on <code>{number}</code> {self.take_this}')
        await evt.respond(content)

    @rt.subcommand('reply', aliases=('re', 'rep'), help='Reply to requestor(s).')
    @command.argument('number', 'ticket number', parser=str)
    @command.argument('text', 'reply text', pass_raw=True)
    async def reply(self, evt: MessageEvent, number: str, text: str) -> None:
        if not self.can_manage(evt) or not self.valid_number(number):
            return
        await evt.mark_read()
        await self._comment(number, 'correspond', text)
        displayname = await self._displayname(evt.room_id, evt.sender)
        content = TextMessageEventContent(
            msgtype=MessageType.NOTICE, format=Format.HTML,
            body=f'{displayname} replied 📨 to {number} {self.take_this}',
            formatted_body=f'<a href="https://matrix.to/#/{evt.sender}">{evt.sender}</a> '
            f'replied 📨 to <code>{number}</code> {self.take_this}')
        await evt.respond(content)

    @rt.subcommand('history', aliases=('h', 'hist'), help='Get a list of all history entries.')
    @command.argument('number', 'ticket number', parser=str)
    async def history(self, evt: MessageEvent, number: str) -> None:
        if not self.can_manage(evt) or not self.valid_number(number):
            return
        await evt.mark_read()
        history_dict = await self._history(number)
        history = '  \n'.join([f'{k}: {v}' for k, v in history_dict.items()])
        await evt.respond(f'{self.markdown_link(number)} history entries:  \n{history}')

    @rt.subcommand('entry', aliases=('e', 'ent'), help='Gets a single history entry.')
    @command.argument('number', 'ticket number', parser=str)
    @command.argument('entryid', 'entry number', parser=str)
    async def entry(self, evt: MessageEvent, number: str, entryid: str) -> None:
        if not self.can_manage(evt) or not self.valid_number(number):
            return
        await evt.mark_read()
        entry_dict = await self._entry(number, entryid)
        entry = '  \n'.join([f'{k}: {v}' for k, v in entry_dict.items()])
        await evt.respond(f'{self.markdown_link(number)} history entry {entryid}:  \n{entry}'
                          f'  \n{self.take_this}')

    @rt.subcommand('last', aliases=('l', 'la'), help='Gets the last entry.')
    @command.argument('number', 'ticket number', parser=str)
    async def last(self, evt: MessageEvent, number: str) -> None:
        if not self.can_manage(evt) or not self.valid_number(number):
            return
        await evt.mark_read()
        history = await self._history(number)
        mails = {k: v for k, v in history.items() if any(i in v for i in self.interesting)}
        entryid = max(mails, key=int)
        entry_dict = await self._entry(number, entryid)
        entry = '  \n'.join([f'{k}: {v}' for k, v in entry_dict.items()])
        await evt.respond(f'{self.markdown_link(number)} history entry {entryid}:  \n{entry}'
                          f'  \n{self.take_this}')

    @rt.subcommand('show', aliases=('s', 'sh'), help='Show all information about the ticket.')
    @command.argument('number', 'ticket number', parser=str)
    async def show(self, evt: MessageEvent, number: str) -> None:
        if not self.can_manage(evt) or not self.valid_number(number):
            return
        await evt.mark_read()
        prop_dict = await self._properties(number)
        props = '  \n'.join([f'{k}: {v}' for k, v in prop_dict.items()])
        await evt.respond(f'{self.markdown_link(number)} properties:  \n{props}')
        history = await self._history(number)
        for entryid, entry_text in history.items():
            if any(i in entry_text for i in self.interesting + ['Requestor']):
                if 'Requestor' in entry_text:
                    await evt.respond(f'history entry {entryid}: {entry_text}')
                    continue
                entry_dict = await self._entry(number, entryid)
                entry = '  \n'.join([f'{k}: {v}' for k, v in entry_dict.items()])
                await evt.respond(f'history entry {entryid}:  \n{entry}')

    @rt.subcommand('take', aliases=('t', 'ta', 'steal'), help='Take or steal the ticket.')
    @command.argument('number', 'ticket number', parser=str)
    async def take(self, evt: MessageEvent, number: str) -> None:
        if not self.can_manage(evt) or not self.valid_number(number):
            return
        await evt.mark_read()
        displayname = await self._displayname(evt.room_id, evt.sender)
        await self._edit(number, {'Owner': evt.sender[1:].split(':')[0]})
        content = TextMessageEventContent(
            msgtype=MessageType.NOTICE, format=Format.HTML,
            body=f'{displayname} took rt#{number} 👍️',
            formatted_body=f'<a href="https://matrix.to/#/{evt.sender}">{evt.sender}</a> '
            f'took {self.html_link(number)} 👍️')
        await evt.respond(content)

    @rt.subcommand('give', aliases=('g', 'gi', 'assign'), help='Give the ticket to somebody.')
    @command.argument('number', 'ticket number', parser=str)
    @command.argument('user', 'matrix user', parser=str)
    async def give(self, evt: MessageEvent, number: str, user: str) -> None:
        if not self.can_manage(evt) or not self.valid_number(number):
            return
        await evt.mark_read()
        member_mxids = await self._member_mxids(evt.room_id)
        if user[0] == '@':
            if ':' in user:
                user = {v: k for k, v in member_mxids.items()}[user]
            else:
                user = user[1:]
        if user not in member_mxids.keys() and user not in member_mxids.values():
            await evt.respond(f'hmm... **{user}** is not the in room 🤔')
            return
        displayname = await self._displayname(evt.room_id, evt.sender)
        target_mxid = member_mxids[user]
        target_username = target_mxid[1:].split(':')[0]
        await self._edit(number, {'Owner': target_username})
        react = f'(\U0001F44D to accept, \U0001F595 to reject)'
        content = TextMessageEventContent(
            msgtype=MessageType.NOTICE, format=Format.HTML,
            body=f'{displayname} assigned rt#{number} to {user} 😜 {react}',
            formatted_body=f'<a href="https://matrix.to/#/{evt.sender}">{evt.sender}</a> '
            f'assigned {self.html_link(number)} to '
            f'<a href="https://matrix.to/#/{target_mxid}">{target_mxid}</a> 😜 {react}')
        await evt.respond(content)

    @rt.subcommand('new', aliases=('n', 'new'), help='List all unowned new/open tickets.')
    async def new(self, evt: MessageEvent) -> None:
        if not self.can_manage(evt):
            return
        await evt.mark_read()
        params = {'query': 'Owner = "Nobody" AND ( Status = "new" OR Status = "open" )'}
        tickets_dict = await self._search(params)
        links = {k: f'[{v}]({self.display}?id={k})' for k, v in tickets_dict.items()}
        tickets = '  \n'.join([f'`{k}`: {links[k]}' for k, v in tickets_dict.items()])
        if tickets:
            await evt.respond(f'Unowned open tickets:  \n{tickets}')
        else:
            await evt.respond('All done ✅')

    @rt.subcommand('mine', aliases=('m', 'my'), help='List all your open tickets.')
    async def mine(self, evt: MessageEvent) -> None:
        if not self.can_manage(evt):
            return
        await evt.mark_read()
        displayname = await self._displayname(evt.room_id, evt.sender)
        username = evt.sender[1:].split(':')[0]
        params = {'query': f'Owner = "{username}" AND ( Status = "new" OR Status = "open" )'}
        tickets_dict = await self._search(params)
        links = {k: f'<a href="{self.display}?id={k}">{v}</a>' for k, v in tickets_dict.items()}
        if tickets_dict:
            body = '\n'.join([f'{k}: {v}' for k, v in tickets_dict.items()])
            fbody = '<br/>'.join([f'<code>{k}</code>: {links[k]}' for k, v in tickets_dict.items()])
            content = TextMessageEventContent(
                msgtype=MessageType.NOTICE, format=Format.HTML,
                body=f'Open tickets for {displayname}:\n{body}',
                formatted_body=f'Open tickets for <a href="https://matrix.to/#/{evt.sender}">'
                f'{evt.sender}</a>:<br/>{fbody}')
            await evt.respond(content)
        else:
            await evt.respond('All done 🤙')

    @rt.subcommand('unsolved', aliases=('u', 'un'), help='List all open tickets.')
    async def unsolved(self, evt: MessageEvent) -> None:
        if not self.can_manage(evt):
            return
        await evt.mark_read()
        params = {'query': f'Status = "new" OR Status = "open"'}
        tickets_dict = await self._search(params)
        links = {k: f'<a href="{self.display}?id={k}">{v}</a>' for k, v in tickets_dict.items()}
        if tickets_dict:
            body = '\n'.join([f'{k}: {v}' for k, v in tickets_dict.items()])
            fbody = '<br/>'.join([f'<code>{k}</code>: {links[k]}' for k, v in tickets_dict.items()])
            content = TextMessageEventContent(
                msgtype=MessageType.NOTICE, format=Format.HTML,
                body=f'Open tickets:\n{body}',
                formatted_body=f'Open tickets:<br/>{fbody}')
            await evt.respond(content)
        else:
            await evt.respond('All done ✅')

    @rt.subcommand('autoresolve', help='Ask the bot to automatically answer and resolve tickets.')
    async def autoresolve(self, evt: MessageEvent) -> None:
        if not self.can_manage(evt):
            return
        await evt.mark_read()
        await evt.react('😂🤣🦄🌈')
