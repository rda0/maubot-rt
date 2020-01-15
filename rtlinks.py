from typing import List, Tuple
from maubot import Plugin, MessageEvent
from maubot.handlers import command


class RTLinksPlugin(Plugin):
    @command.passive("((^| )([rR][tT]#?))([0-9]{6})", multiple=True)
    async def handler(self, evt: MessageEvent, subs: List[Tuple[str, str]]) -> None:
        await evt.mark_read()
        msg_lines = []
        for sub in subs:
            number = sub[4]
            link = "https://rt.phys.ethz.ch/rt/Ticket/Display.html?id={}".format(number)
            markdown = "[rt#{}]({})".format(number, link)
            msg_lines.append(markdown)

        if msg_lines:
            await evt.respond("\n".join(msg_lines))
