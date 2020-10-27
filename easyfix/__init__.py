import datetime
import re
from queue import Queue
from typing import Dict, List, Optional, Tuple

import lxml
import lxml.etree
import quickfix as fix
from loguru import logger


def disable_logging():
    logger.disable('easyfix')


def enable_logging():
    logger.enable('easyfix')


def parse_config(config_filename: str) -> dict:
    with open(config_filename, 'r') as f:
        return {
            xs[0]: ''.join(xs[1:])
            for l in f if (
                not l.startswith(';')
                and len(xs := l.strip().split('=')) > 1
            )
        }


def fix_utctimestamp(t: datetime.datetime) -> str:
    return t.strftime('%Y%m%d-%H:%M:%S.%f')[:-3]


def parse_enums(data_dictionary_filename: str) -> Dict[str, Dict[str, str]]:
    with open(data_dictionary_filename, 'r') as f:
        doc = lxml.etree.parse(f)
        stack: List[Tuple[str, Dict[str, str]]] = []

        rv = {}

        for action, elem in lxml.etree.iterwalk(doc, ("start", "end")):
            tag = elem.tag
            if "}" in tag:
                tag = tag[tag.index("}") + 1:]

            if tag == "field":
                if action == "start":
                    attrs = dict(elem.items())
                    stack.append((attrs['name'], {}))

                elif action == "end":
                    k, x = stack.pop()
                    if x:
                        rv[k] = x

            elif tag == "value":
                if action == "start":
                    attrs = dict(elem.items())
                    if 'enum' in attrs:
                        stack[-1][1][attrs['enum']] = attrs.get('description', attrs['enum'])

                elif action == "end":
                    pass

        return rv


class InitiatorApp(fix.Application):
    session_id = None
    session: fix.Session

    data_dict: fix.DataDictionary

    uesrname: Optional[str]
    password: Optional[str]

    logged_on = False
    autofix_sequence_numbers = True

    socket_initiator: fix.SocketInitiator

    outgoing_messages: "Queue[fix.Message]"
    incoming_messages: "Queue[fix.Message]"
    enums: Dict[str, Dict[str, str]]

    @property
    def to_messages(self):
        return self.outgoing_messages

    @property
    def from_messages(self):
        return self.incoming_messages

    @classmethod
    def create(cls, config_filename: str):
        config = parse_config(config_filename)

        rv = cls()

        rv.incoming_messages = Queue()
        rv.outgoing_messages = Queue()

        rv.data_dict = fix.DataDictionary(config['DataDictionary'])
        rv.enums = parse_enums(config['DataDictionary'])
        rv.username = config.get('Username')
        rv.password = config.get('Password')

        settings = fix.SessionSettings(config_filename)
        rv.socket_initiator = fix.SocketInitiator(
            rv, fix.FileStoreFactory(settings), settings, fix.FileLogFactory(settings))

        return rv

    def start(self):
        self.socket_initiator.start()

    def stop(self):
        self.socket_initiator.stop()

    def parse(self, m: fix.Message, debug=False) -> dict:
        return self.fix_to_dict(m, debug)

    def get_field_tag(self, tag_name: str) -> int:
        return self.data_dict.getFieldTag(tag_name, "")[0]

    def get_field_name(self, tag: int) -> str:
        return self.data_dict.getFieldName(tag, "")[0]

    def humanize(self, m: fix.Message, debug=True):
        rv = []

        for x in (x for x in m.toString().split("\x01") if x.strip()):
            tag = x.split("=")[0]
            value = "".join(x.split("=")[1:])

            tag_name = self.get_field_name(int(tag))
            k = f"{tag_name}({tag})" if debug else tag_name

            if tag_name in self.enums and value in self.enums[tag_name]:
                value = self.enums[tag_name][value] + f"({value})"

            rv.append(f"{k}={value}")

        return "|".join(rv)

    def get_fields_by_name(self, m: fix.Message, field_name: str) -> List[str]:
        st = self.humanize(m, debug=False)
        return [''.join(l.split("=")[1:]) for l in st.split("|") if l.split("=")[0] == field_name]

    def fix_to_dict(self, m: fix.Message, debug=False):
        rv = {}

        for x in (x for x in m.toString().split("\x01") if x.strip()):
            tag = x.split("=")[0]
            value = "".join(x.split("=")[1:])

            tag_name = self.get_field_name(int(tag))
            k = f"{tag_name}({tag})" if debug else tag_name

            if tag_name in self.enums and value in self.enums[tag_name]:
                value = self.enums[tag_name][value] + f"({value})"

            rv[k] = value

        return rv

    def onCreate(self, session_id: fix.SessionID):
        logger.info(f"onCreate: {session_id}")
        self.session_id = session_id
        self.session = fix.Session.lookupSession(self.session_id)

    def onLogon(self, session_id: fix.SessionID):
        logger.info(f"onLogon: {session_id}")
        self.logged_on = True

    def onLogout(self, session_id: fix.SessionID):
        logger.info(f"onLogout: {session_id}")
        self.logged_on = False

    def log_message(self, from_func: str, m: fix.Message, session_id: fix.SessionID, levelize=True):
        logger.debug("{}: {} {}", from_func, m.toString().replace("\x01", "|"), session_id)

        m1 = self.fix_to_dict(m, True)
        msg_type = m.getHeader().getField(fix.MsgType().getTag())

        if not levelize:
            logger.info(f"{from_func}: {m1} {session_id}")
            return

        if msg_type == fix.MsgType_Reject:
            logger.error(f"{from_func}: {m1} {session_id}")
        elif msg_type == fix.MsgType_Heartbeat:
            logger.debug(f"{from_func}: {m1} {session_id}")
        elif msg_type == fix.MsgType_Logout and m.isSetField(fix.Text().getTag()):
            logger.error(f"{from_func}: {m1} {session_id}")
        else:
            logger.info(f"{from_func}: {m1} {session_id}")

    def toAdmin(self, m: fix.Message, session_id: fix.SessionID):
        if self.username and self.password:
            if m.getHeader().getField(fix.MsgType().getTag()) == fix.MsgType_Logon:
                m.setField(fix.Username(self.username))
                m.setField(fix.Password(self.password))

        if self.autofix_sequence_numbers:
            text_tag = fix.Text().getTag()
            is_seqnum_too_low = (
                m.getHeader().getField(fix.MsgType().getTag()) == fix.MsgType_Logout
                and m.isSetField(text_tag)
                and m.getField(text_tag).startswith("MsgSeqNum too low")
            )

            if is_seqnum_too_low:
                needed_seqnum = int(re.match("MsgSeqNum too low, expecting (\d+) but received (\d+)", m.getField(text_tag))[2])

                self.log_message("toAdmin", m, session_id, levelize=False)
                logger.warning(f"Resetting MsgSeqNum to {needed_seqnum} as needed. Wait for reconnect...")

                self.session.setNextTargetMsgSeqNum(needed_seqnum)
                return

        self.log_message("toAdmin", m, session_id)
        self.outgoing_messages.put(fix.Message(m))

    def toApp(self, m: fix.Message, session_id: fix.SessionID):
        self.log_message("toApp", m, session_id)
        self.outgoing_messages.put(fix.Message(m))

    def fromAdmin(self, m: fix.Message, session_id: fix.SessionID):
        if self.autofix_sequence_numbers:
            text_tag = fix.Text().getTag()
            is_seqnum_too_low = (
                m.getHeader().getField(fix.MsgType().getTag()) == fix.MsgType_Logout
                and m.isSetField(text_tag)
                and m.getField(text_tag).startswith("MsgSeqNum too low")
            )

            if is_seqnum_too_low:
                needed_seqnum = int(re.match("MsgSeqNum too low, expecting (\d+)", m.getField(text_tag))[1])

                self.log_message("fromAdmin", m, session_id, levelize=False)
                logger.warning(f"Resetting MsgSeqNum to {needed_seqnum} as needed. Wait for reconnect...")

                self.session.setNextSenderMsgSeqNum(needed_seqnum)
                return

        self.log_message("fromAdmin", m, session_id)
        self.incoming_messages.put(fix.Message(m))

    def fromApp(self, m: fix.Message, session_id: fix.SessionID):

        self.log_message("fromApp", m, session_id)
        self.incoming_messages.put(fix.Message(m))


disable_logging()
