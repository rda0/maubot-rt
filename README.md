# RT Links Maubot
A [maubot](https://github.com/maubot/maubot) that sends clickable markdown formatted links when it sees RT ticket numbers in a given format.

## Usage
- `rt123456` - Responds with `[123456](https://rt.phys.ethz.ch/rt/Ticket/Display.html?id=123456)`
- `!rt` - Show the help

```
Usage: !rt <subcommand> [...]

    properties <ticket number> - Show all ticket properties.
    resolve <ticket number> - Mark the ticket as resolved.
    open <ticket number> - Mark the ticket as open.
    stall <ticket number> - Mark the ticket as stalled.
    delete <ticket number> - Mark the ticket as deleted.
    autoresolve - Enable automatic ticket resolve mode.
    comment <ticket number> <comment text> - Add a comment.
    history <ticket number> - Get a list of all history items for a given ticket.
    entry <ticket number> <history entry number> - Gets the history information for a single history entry.
    last <ticket number> - Gets the history information for the last history entry.
    show <ticket number> - Show all information about the ticket.
```
