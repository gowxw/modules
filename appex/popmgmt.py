#!/usr/bin/python
import logging
import apxpublish
import apxconsume
import time
import pika
import threading
import functools
import fcntl
import os
import pwd
import grp
import sys
import signal
import resource
import atexit
import traceback
import redis

log = logging.getLogger("agent")
hdl = logging.FileHandler("./pop_stats_log.log")
fmt = logging.Formatter(fmt="[%(asctime)s %(threadName)s %(filename)s %(funcName)s %(lineno)d] %(message)s")
hdl.setFormatter(fmt)
log.addHandler(hdl)
log.setLevel(logging.INFO)

pool = redis.ConnectionPool(host='127.0.0.1', port=6379, db=0)
redisconn = redis.Redis(connection_pool=pool)

publish_connection = None
consumer_connection = None
pid_dir = "./agent_pid"

class Daemonize(object):
    """
    Daemonize object.
    Object constructor expects three arguments.
    :param app: contains the application name which will be sent to syslog.
    :param pid: path to the pidfile.
    :param action: your custom function which will be executed after daemonization.
    :param keep_fds: optional list of fds which should not be closed.
    :param auto_close_fds: optional parameter to not close opened fds.
    :param privileged_action: action that will be executed before drop privileges if user or
                              group parameter is provided.
                              If you want to transfer anything from privileged_action to action, such as
                              opened privileged file descriptor, you should return it from
                              privileged_action function and catch it inside action function.
    :param user: drop privileges to this user if provided.
    :param group: drop privileges to this group if provided.
    :param verbose: send debug messages to logger if provided.
    :param logger: use this logger object instead of creating new one, if provided.
    :param foreground: stay in foreground; do not fork (for debugging)
    :param chdir: change working directory if provided or /
    """
    def __init__(self, pid, action,logger,
                 keep_fds=None, auto_close_fds=True, privileged_action=None,
                 user=None, group=None, verbose=False,
                 foreground=False, chdir="/"):
        self.pid = os.path.abspath(pid)
        self.action = action
        self.keep_fds = keep_fds or []
        self.privileged_action = privileged_action or (lambda: ())
        self.user = user
        self.group = group
        self.logger = logger
        self.verbose = verbose
        self.auto_close_fds = auto_close_fds
        self.foreground = foreground
        self.chdir = chdir

    def sigterm(self, signum, frame):
        """
        These actions will be done after SIGTERM.
        """
        self.logger.warn("Caught signal %s. Stopping popmgmt." % signum)
        sys.exit(0)

    def exit(self):
        """
        Cleanup pid file at exit.
        """
        self.logger.warn("Stopping popmgmt.")
        os.remove(self.pid)
        sys.exit(0)

    def cmds(self, signum, frame):
        self.logger.warn("hahahaha %d %r",signum,type(frame))

    def start(self):
        """
        Start daemonization process.
        """
        # If pidfile already exists, we should read pid from there; to overwrite it, if locking
        # will fail, because locking attempt somehow purges the file contents.
        if os.path.isfile(self.pid):
            with open(self.pid, "r") as old_pidfile:
                old_pid = old_pidfile.read()
        # Create a lockfile so that only one instance of this daemon is running at any time.
        try:
            lockfile = open(self.pid, "w")
        except IOError:
            print("Unable to create the pidfile.")
            sys.exit(1)
        try:
            # Try to get an exclusive lock on the file. This will fail if another process has the file
            # locked.
            fcntl.flock(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError:
            print("popmgmt is running")
            self.logger.error("popmgmt is running.")
            # We need to overwrite the pidfile if we got here.
            with open(self.pid, "w") as pidfile:
                pidfile.write(old_pid)
            sys.exit(1)

        # skip fork if foreground is specified
        if not self.foreground:
            # Fork, creating a new process for the child.
            try:
                process_id = os.fork()
            except OSError as e:
                self.logger.error("Unable to fork, errno: {0}".format(e.errno))
                sys.exit(1)
            if process_id != 0:
                # This is the parent process. Exit without cleanup,
                # see https://github.com/thesharp/daemonize/issues/46
                os._exit(0)
            # This is the child process. Continue.

            # Stop listening for signals that the parent process receives.
            # This is done by getting a new process id.
            # setpgrp() is an alternative to setsid().
            # setsid puts the process in a new parent group and detaches its controlling terminal.
            process_id = os.setsid()

            if process_id == -1:
                # Uh oh, there was a problem.
                sys.exit(1)
            # Add lockfile to self.keep_fds.
            self.keep_fds.append(lockfile.fileno())
            # Close all file descriptors, except the ones mentioned in self.keep_fds.
            devnull = "/dev/null"
            if hasattr(os, "devnull"):
                # Python has set os.devnull on this system, use it instead as it might be different
                # than /dev/null.
                devnull = os.devnull

            if self.auto_close_fds:
                for fd in range(3, resource.getrlimit(resource.RLIMIT_NOFILE)[0]):
                    if fd not in self.keep_fds:
                        try:
                            os.close(fd)
                        except OSError:
                            pass
            devnull_fd = os.open(devnull, os.O_RDWR)
            os.dup2(devnull_fd, 0)
            os.dup2(devnull_fd, 1)
            os.dup2(devnull_fd, 2)
            os.close(devnull_fd)


        # Set umask to default to safe file permissions when running as a root daemon. 027 is an
        # octal number which we are typing as 0o27 for Python3 compatibility.
        os.umask(0o27)

        # Change to a known directory. If this isn't done, starting a daemon in a subdirectory that
        # needs to be deleted results in "directory busy" errors.
        os.chdir(self.chdir)

        # Execute privileged action
        privileged_action_result = self.privileged_action()
        if not privileged_action_result:
            privileged_action_result = []

        # Change owner of pid file, it's required because pid file will be removed at exit.
        uid, gid = -1, -1

        if self.group:
            try:
                gid = grp.getgrnam(self.group).gr_gid
            except KeyError:
                self.logger.error("Group {0} not found".format(self.group))
                sys.exit(1)

        if self.user:
            try:
                uid = pwd.getpwnam(self.user).pw_uid
            except KeyError:
                self.logger.error("User {0} not found.".format(self.user))
                sys.exit(1)

        if uid != -1 or gid != -1:
            os.chown(self.pid, uid, gid)

        # Change gid
        if self.group:
            try:
                os.setgid(gid)
            except OSError:
                self.logger.error("Unable to change gid.")
                sys.exit(1)

        # Change uid
        if self.user:
            try:
                uid = pwd.getpwnam(self.user).pw_uid
            except KeyError:
                self.logger.error("User {0} not found.".format(self.user))
                sys.exit(1)
            try:
                os.setuid(uid)
            except OSError:
                self.logger.error("Unable to change uid.")
                sys.exit(1)

        try:
            lockfile.write("%s" % (os.getpid()))
            lockfile.flush()
        except IOError:
            self.logger.error("Unable to write pid to the pidfile.")
            print("Unable to write pid to the pidfile.")
            sys.exit(1)

        # Set custom action on SIGTERM.
        signal.signal(signal.SIGTERM, self.sigterm)
        atexit.register(self.exit)

        signal.signal(signal.SIGUSR1, self.cmds)

        self.logger.warn("Starting popmgmt.")

        try:
            self.action(*privileged_action_result)
        except Exception:
            for line in traceback.format_exc().split("\n"):
                self.logger.error(line)



def send_entry():
    publish_connection.run()

def recv_entry():
    consumer_connection.run()

def report_entry():
    while True:
        if publish_connection._connection:
            try:
                log.debug("send msg")
                msg = 'abcdefg' + str(publish_connection._message_number)
                publish_connection._connection.add_timeout(0, functools.partial(publish_connection.publish_message,
                                                                                msg))
            except Exception as e:
                log.warning('publish connection not ready2 %s', e)
                pass
            time.sleep(1)
        else:
            log.info('publish connection not ready1')
            time.sleep(1)


def start():
    global publish_connection
    global consumer_connection
    credentials = pika.PlainCredentials('admin', 'admin')
    parameters = pika.ConnectionParameters(host="10.1.5.5",
                                           port=5672,
                                           credentials=credentials,
                                           socket_timeout=2,
                                           connection_attempts=3,
                                           heartbeat=3600)

    publish_connection = apxpublish.apxPublisher(parameters)
    publish_connection.EXCHANGE = 'topic_to_edge'
    publish_connection.ROUTING_KEY = 'edge.B6B761BFC9F5C2C4'

    consumer_connection = apxconsume.apxConsumer(parameters)
    consumer_connection.EXCHANGE = 'topic_to_edge'
    consumer_connection.ROUTING_KEY = 'edge.B6B761BFC9F5C2C4'
    consumer_connection.QUEUE = 'queue_edge_B6B761BFC9F5C2C4'


    send_thread = threading.Thread(target=send_entry, name="publish")
    send_thread.daemon = True
    send_thread.start()

    recv_thread = threading.Thread(target=recv_entry, name="consume")
    recv_thread.daemon =True
    recv_thread.start()

    report_thread = threading.Thread(target=report_entry, name="report")
    report_thread.daemon = True
    report_thread.start()

    while True:
        try:
            res = redisconn.blpop("popmgmt_sig")
            log.warning("get signal %s %s",res[0],res[1])
            if res[1] == "open msg":
                log.setLevel(logging.DEBUG)
            if res[1] == "close msg":
                log.setLevel(logging.INFO)
        except redis.RedisError as e:
            log.error("connect redis error %s",e)
            exit(1)


if __name__ == '__main__':
    if len(sys.argv) == 1:
        print 'usage'
        exit(1)

    if len(sys.argv) == 2:
        if sys.argv[1] == 'start':
            d = Daemonize(pid_dir, start, log, auto_close_fds = False)
            d.start()
        elif sys.argv[1] == 'stop':
            try:
                log.warning("popmgmt stop.")
                with open(pid_dir,'r') as f:
                    pid = f.read()
                    try:
                        os.kill(int(pid),signal.SIGKILL)
                    except Exception:
                        pass
                    try:
                        os.remove(pid_dir)
                    except Exception:
                        pass
            except IOError:
                print "popmgmt is stopped"
        elif sys.argv[1] == 'status':
            try:
                lockfile = open(pid_dir, "r")
            except IOError:
                print "popmgmt is stopped"
                sys.exit(1)
            try:
                # Try to get an exclusive lock on the file. This will fail if another process has the file
                # locked.
                fcntl.flock(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except IOError:
                print("popmgmt is running")
                log.warning("popmgmt is running.")

    if len(sys.argv) == 3:
        if sys.argv[1] == 'open' and sys.argv[2] == 'msg':
            try:
                redisconn.rpush("popmgmt_sig","open msg")
            except redis.RedisError:
                print "error"

        if sys.argv[1] == 'close' and sys.argv[2] == 'msg':
            try:
                redisconn.rpush("popmgmt_sig","close msg")
            except redis.RedisError:
                print "error"


