import datetime
import time
import uuid

import quickfix as fix
import quickfix44 as fix44

import easyfix

if __name__ == '__main__':
    # Get your FIX dictionary at http://www.quickfixengine.org or your
    # connection target
    with open('example.cfg', 'w') as f:
        f.write("""[DEFAULT]
FileStorePath=./sessions
FileLogPath=./logs
ConnectionType=initiator

[SESSION]
BeginString=FIX.4.4
DataDictionary=FIX44.xml

SocketConnectProtocol=SOCKET
SocketConnectHost=localhost
SocketConnectPort=1234
TargetCompID=your-comp-id

SenderCompID=1234
Username=user@example.com
Password=a-long-password

StartTime=00:00:00
EndTime=00:00:00
HeartBtInt=30
ReconnectInterval=10"""
                )

    easyfix.enable_logging()

    app = easyfix.InitiatorApp.create('example.cfg')
    app.start()

    while not app.logged_on:
        time.sleep(0.1)

    print("Logged in!")

    # Send message using normal Quickfix messages
    m = fix44.SecurityListRequest()
    m.setField(fix.SecurityReqID(str(uuid.uuid4())))
    m.setField(fix.SecurityListRequestType(fix.SecurityListRequestType_ALL_SECURITIES))
    fix.Session.sendToTarget(m, app.session_id)

    # Send an order
    m = fix44.NewOrderSingle()
    m.setField(fix.ClOrdID(str(uuid.uuid4())))
    m.setField(fix.SecurityID('25'))
    m.setField(fix.SecurityIDSource(fix.SecurityIDSource_MARKETPLACE_ASSIGNED_IDENTIFIER))
    m.setField(fix.Side(fix.Side_BUY))
    m.setField(fix.OrderQty(0.01))
    m.setField(fix.Price(123))
    m.setField(fix.OrdType(fix.OrdType_LIMIT))

    # Python QuickFIX UtcTimeStampField doesn't accept a `datetime` object, we
    # provide an easy helper function for you
    t = fix.TransactTime()
    t.setString(easyfix.fix_utctimestamp(datetime.datetime.utcnow()))
    m.setField(t)
    fix.Session.sendToTarget(m, app.session_id)

    # Some sort of main loop
    while m := app.incoming_messages.get():
        # Get field(s) by name
        #
        # Note that this does not consider repeating group hierarchies and dump
        # all fields matching the tag of the name
        print(app.get_fields_by_name(m, 'MsgType'))
        print(app.get_fields_by_name(m, 'Symbol'))

        # Get "nicely" formatted FIX message dump. Enums are automatically converted to descriptions
        #
        # Example:
        #
        #   BeginString=FIX.4.4|BodyLength=736|MsgType=SECURITY_LIST|MsgSeqNum=1039|...
        print(app.humanize(m))
