# easyfix

Easy to use, low-boilerplate wrapper for [QuickFIX](http://www.quickfixengine.org/) (initiator only for now).

## Motivation

Setting up a FIX application with [QuickFIX](http://www.quickfixengine.org/) is a lot of boilerplate. This is your easy fix.

This is mainly intended to experiment and explore with a FIX counterparty, or to be used in test cases. There is no effort made to make this suitable in a high performance setting.

## Install

```bash
pip install easyfix
```

QuickFIX is not installed automatically, if you don't have it already:

```bash
pip install quickfix
```

## Features

- Minimalistic API for quick and no fuss FIX API exploration
- Humanized output: converts enum fields to descriptions -- no more spending hours digging through FIX references
- Automatically set your sequence number to the needed value if your counterparty tells you "MsgSeqNum too low". Just restarting your app if your connection gets hung usually fixes it.

## Usage

More examples at [example.py](example.py)

### Initiator

```python
import quickfix as fix
import quickfix44 as fix44
import easyfix

# Enable verbose logging for troubleshooting
# easyfix.enable_logging()

# Finally, no need to create a whole class just to connect to a FIX server!
app = easyfix.InitiatorApp.create('example.cfg')
app.start()

while not app.logged_on:
    time.sleep(0.1)

print("Logged in!")

# Send message using normal QuickFIX messages
m = fix44.SecurityListRequest()
m.setField(fix.SecurityReqID(str(uuid.uuid4())))
m.setField(fix.SecurityListRequestType(fix.SecurityListRequestType_ALL_SECURITIES))
fix.Session.sendToTarget(m, app.session_id)

# Pull messages from a Queue
while m := app.incoming_messages.get():
    # Get field(s) by name
    #
    # Note that this does not consider repeating group hierarchies and dump
    # all fields matching the tag of the name
    #
    # Example output:
    #
    #   ["SecurityList"]
    #   ["BTC/USD", "ETH/BTC"]
    print(app.get_fields_by_name(m, 'MsgType'))
    print(app.get_fields_by_name(m, 'Symbol'))

    # Get "nicely" formatted FIX message dump. Enums are automatically converted to descriptions
    #
    # Example output:
    #
    #   BeginString=FIX.4.4|BodyLength=736|MsgType=SECURITY_LIST(y)|MsgSeqNum=1039|...
    print(app.humanize(m))
```

### Verbose logging

You can get dump of FIX messages by enabling logging:

```python
easyfix.enable_logging()
```
