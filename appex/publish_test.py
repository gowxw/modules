#向brocker发送消息实例程序
#三个抓包文件：分别是kill broker process、power-off broker、正常发送消息，三种情况的抓包

import functools
import logging
import pika
import json
import threading
import time

log = logging.getLogger("agent")

log = logging.getLogger("agent")
#hdl = logging.FileHandler("/var/log/popmgmt.log")
hdl = logging.StreamHandler()
fmt = logging.Formatter(fmt="[%(asctime)s pid:%(processName)s-%(process)d %(threadName)s %(filename)s line:%(lineno)d] %(message)s")
hdl.setFormatter(fmt)
log.addHandler(hdl)
log.setLevel(logging.DEBUG)


class apxPublisher(object):
    """This is an example publisher that will handle unexpected interactions
    with RabbitMQ such as channel and connection closures.
    If RabbitMQ closes the connection, it will reopen it. You should
    look at the output, as there are limited reasons why the connection may
    be closed, which usually are tied to permission related issues or
    socket timeouts.
    It uses delivery confirmations and illustrates one way to keep track of
    messages that have been sent and if they've been confirmed by RabbitMQ.
    """

    def __init__(self, amqp_parameter):
        """Setup the example publisher object, passing in the URL we will use
        to connect to RabbitMQ.
        :param str amqp_url: The URL for connecting to RabbitMQ
        """
        self._connection = None
        self._channel = None
        self._message_number = None

        self._stopping = False
        self._parameter = amqp_parameter
        self._nowpara = None
        self._ready = False

    def connect(self):
        """This method connects to RabbitMQ, returning the connection handle.
        When the connection is established, the on_connection_open method
        will be invoked by pika. If you want the reconnection to work, make
        sure you set stop_ioloop_on_close to False, which is not the default
        behavior of this adapter.
        :rtype: pika.SelectConnection
        """
        #self._nowpara = self._parameter.pop(0)
        #self._parameter.append(self._nowpara)

        log.info('Connecting to %s:%d', self._parameter.host, self._parameter.port)

        return pika.SelectConnection(self._parameter,
                                     on_open_callback=self.on_connection_open,
                                     on_open_error_callback=self.on_connection_open_error,
                                     on_close_callback=self.on_connection_closed,
                                     stop_ioloop_on_close=False)

    def on_connection_open(self, unused_connection):
        """This method is called by pika once the connection to RabbitMQ has
        been established. It passes the handle to the connection object in
        case we need it, but in this case, we'll just mark it unused.
        :type unused_connection: pika.SelectConnection
        """
        log.info('Connection opened')
        self.open_channel()

    def on_connection_open_error(self, unused_connection, err):
        """This method is called by pika if the connection to RabbitMQ
        can't be established.
        :type unused_connection: pika.SelectConnection
        :type err: str
        """
        log.error('Connection open failed: %s', err)
        self._connection.add_timeout(3, self._connection.ioloop.stop)

    def on_connection_closed(self, connection, reply_code, reply_text):
        """This method is invoked by pika when the connection to RabbitMQ is
        closed unexpectedly. Since it is unexpected, we will reconnect to
        RabbitMQ if it disconnects.
        :param pika.connection.Connection connection: The closed connection obj
        :param int reply_code: The server provided reply_code if given
        :param str reply_text: The server provided reply_text if given
        """
        self._channel = None
        if self._stopping:
            self._connection.ioloop.stop()
        else:
            log.warning('Connection closed,reconnect to %s:%d', self._parameter.host, self._parameter.port)
            self._connection.add_timeout(0, self._connection.ioloop.stop)

    def open_channel(self):
        """This method will open a new channel with RabbitMQ by issuing the
        Channel.Open RPC command. When RabbitMQ confirms the channel is open
        by sending the Channel.OpenOK RPC reply, the on_channel_open method
        will be invoked.
        """
        log.info('Creating a new channel')
        self._connection.channel(on_open_callback=self.on_channel_open)

    def on_channel_open(self, channel):
        """This method is invoked by pika when the channel has been opened.
        The channel object is passed in so we can make use of it.
        Since the channel is now open, we'll declare the exchange to use.
        :param pika.channel.Channel channel: The channel object
        """
        log.info('Channel opened')
        self._channel = channel
        self.add_on_channel_close_callback()

    def add_on_channel_close_callback(self):
        """This method tells pika to call the on_channel_closed method if
        RabbitMQ unexpectedly closes the channel.
        """
        log.info('Adding channel close callback')
        self._channel.add_on_close_callback(self.on_channel_closed)
        self._ready = True

    def on_channel_closed(self, channel, reply_code, reply_text):
        """Invoked by pika when RabbitMQ unexpectedly closes the channel.
        Channels are usually closed if you attempt to do something that
        violates the protocol, such as re-declare an exchange or queue with
        different parameters. In this case, we'll close the connection
        to shutdown the object.
        :param pika.channel.Channel channel: The closed channel
        :param int reply_code: The numeric reason the channel was closed
        :param str reply_text: The text reason the channel was closed
        """
        log.warning('Channel was closed: (%s) %s', reply_code, reply_text)
        self._channel = None
        self._ready = False
        if not self._stopping:
            self._connection.close()

    def publish_message(self,exchange,msg):
        """If the class is not stopping, publish a message to RabbitMQ,
        appending a list of deliveries with the message number that was sent.
        This list will be used to check for delivery confirmations in the
        on_delivery_confirmations method.
        Once the message has been sent, schedule another message to be sent.
        The main reason I put scheduling in was just so you can get a good idea
        of how the process is flowing by slowing down and speeding up the
        delivery intervals by changing the PUBLISH_INTERVAL constant in the
        class.
        """
        if self._channel is None or not self._channel.is_open:
            log.warning('Publish connection not ready')
            return

        try:
            self._channel.basic_publish(exchange, self.ROUTING_KEY,
                                    msg,properties = None)
        except pika.exceptions.AMQPError as e:
            log.warning('exception %r', e)


        self._message_number += 1
        #self.schedule_next_message()

    def run(self):
        """Run the example code by connecting and then starting the IOLoop.
        """
        while not self._stopping:
            self._connection = None
            self._message_number = 0

            try:
                self._connection = self.connect()
                log.info("---%s---start ",self._connection)
                self._connection.ioloop._poller._MAX_POLL_TIMEOUT = 0.5
                #LOGGER.warning("%d", self._connection.ioloop._poller._MAX_POLL_TIMEOUT)
                self._connection.ioloop.start()
                log.info("---%s---end", self._connection)
            except KeyboardInterrupt:
                self.stop()
                if (self._connection is not None and
                        not self._connection.is_closed):
                    # Finish closing
                    self._connection.ioloop.start()

        log.info('Stopped')

    def stop(self):
        """Stop the example by closing the channel and connection. We
        set a flag here so that we stop scheduling new messages to be
        published. The IOLoop is started because this method is
        invoked by the Try/Catch below when KeyboardInterrupt is caught.
        Starting the IOLoop again will allow the publisher to cleanly
        disconnect from RabbitMQ.
        """
        log.info('Stopping')
        self._stopping = True
        self.close_channel()
        self.close_connection()

    def close_channel(self):
        """Invoke this command to close the channel with RabbitMQ by sending
        the Channel.Close RPC command.
        """
        if self._channel is not None:
            log.info('Closing the channel')
            self._channel.close()

    def close_connection(self):
        """This method closes the connection to RabbitMQ."""
        if self._connection is not None:
            log.info('Closing connection')
            self._connection.close()



credentials = pika.PlainCredentials('admin', 'admin')


_para = pika.ConnectionParameters(host="10.1.3.100",
                                  port=5672,
                                  credentials=credentials,
                                  socket_timeout=2,
                                  connection_attempts=3,
                                  heartbeat=20)



def func():
    time.sleep(3)
    while True:
        time.sleep(2)
        print publiser._message_number
        if publiser._message_number < 10:
            publiser.publish_message('topic_to_orchestrator',str(time.time()))


t1 = threading.Thread(target=func)
t1.daemon =True
t1.start()

publiser = apxPublisher(_para)
publiser.ROUTING_KEY = 'orchestrator.2'
publiser.run()

