# RT Maubot
A [maubot](https://github.com/maubot/maubot) for [RequestTracker](https://bestpractical.com/request-tracker)

## Features
- Responds with some information about tickets if it sees RT ticket numbers in a given format
- Implements basic functionality for interacting with RT
- Assumes that the mxid localpart is equal to the RT username
- Uses the REST 1.0 interface
- Tested with `request-tracker4` on Debian

## Usage
- `rt123` - Responds with ticket information
- `!rt` - Shows the help text
