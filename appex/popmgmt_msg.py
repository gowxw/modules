import json
import logging


LOGGER = logging.getLogger("agent")
login_or_not = False


def msg_head(action,popid,controllerid):
    header = dict()
    header['action'] = action
    header['from'] = popid
    header['to'] = controllerid
    header['sender'] = "pop"
    header['params'] = dict()
    return header

def proc_login_msg(params):
    global login_or_not
    res = params['result']
    if res == 'ok':
        LOGGER.info("ok %s", res)
        login_or_not = True
    else:
        LOGGER.info("fail %s", res)

def recv_msg(msg):
    try:
        msg_body = json.loads(msg)
    except Exception as e:
        LOGGER.debug("%r", e)
        return

    try:
        action = msg_body['action']
        params = msg_body['params']
        if action == 'loginReply':
            proc_login_msg(params)
    except  Exception as e:
        LOGGER.error("%r",e)
        return





