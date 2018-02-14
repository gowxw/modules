#!/usr/bin/python
import logging
import apxpublish
import apxconsumer
import time
import pika
import threading
import functools

log = logging.getLogger("agent")
hdl = logging.FileHandler("./pop_stats_log.log")
fmt = logging.Formatter(fmt="[%(asctime)s %(process)d %(processName)s %(threadName)s %(filename)s %(funcName)s %(lineno)d] %(message)s")
hdl.setFormatter(fmt)
#log.addHandler(hdl)
streamhdl = logging.StreamHandler()
streamhdl.setFormatter(fmt)
log.addHandler(streamhdl)
log.setLevel(logging.INFO)


credentials = pika.PlainCredentials('admin', 'admin')
parameters = pika.ConnectionParameters(host="47.88.15.149",
                                        port=5672,
                                        credentials=credentials,
                                        socket_timeout=2,
                                        connection_attempts = 3,
                                        heartbeat = 3600)

publish_connection = apxpublish.apxPublisher(parameters)
publish_connection.EXCHANGE = 'topic_to_agent'
publish_connection.ROUTING_KEY = 'agent.18'


consumer_connection = apxconsumer.apxConsumer(parameters)
consumer_connection.EXCHANGE = 'topic_to_agent'
consumer_connection.ROUTING_KEY = 'agent.18'
consumer_connection.QUEUE = 'queue_agent_18'


def send_entry():
    publish_connection.run()

send_thread = threading.Thread(target=send_entry,name="publish")
send_thread.start()


def recv_entry():
    consumer_connection.run()

recv_thread = threading.Thread(target=recv_entry,name="consume")
recv_thread.start()


def report_entry():
    while True:
        if publish_connection._connection:
            time.sleep(1)
            try:
                log.warning("send msg")
                msg = 'abcdefg'
                publish_connection._connection.add_timeout(0, functools.partial(publish_connection.publish_message, msg))
            except Exception as e:
                log.warning('publish connection not ready2 %s', e)
                pass
        else:
            log.info('publish connection not ready1')
            time.sleep(1)

report_thread = threading.Thread(target=report_entry,name="report")
report_thread.start()







