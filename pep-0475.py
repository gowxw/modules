'''
https://www.python.org/dev/peps/pep-0475/

System call wrappers provided in the standard library should be retried automatically when they fail with EINTR, to relieve application code from the burden of doing so.
'''

import socket
import time
import signal

def handler(signo,frame):
    print('receive sig %d',signo)
signal.signal(signal.SIGUSR1,handler)

def blocking_get():
    sock = socket.socket()
    try:
        sock.connect(('www.example.com',80))
    except BlockingIOError:
        pass
    request = 'GET / HTTP/1.1\r\nHost: www.example.com\r\n\r\n'
    data = request.encode('ascii')

    while True:
        try:
            r=sock.send(data)
            break
        except OSError:
            pass
    response = b''

    trunk = sock.recv(4096)
    while trunk:
        response += trunk
        trunk = sock.recv(4096)
        print(trunk)
    return response


blocking_get()

'''
run this script and send signal to the process as it blocks at socket.recv
send signal to process

signal(817, signal.SIGUSER1)

on python2.7,it receive the signal and raise Interrupted
('receive sig %d', 30)
Traceback (most recent call last):
  File "pep-0475.py", line 40, in <module>
    blocking_get()
  File "pep-0475.py", line 35, in blocking_get
    trunk = sock.recv(4096)
socket.error: [Errno 4] Interrupted system call


on python3.5,it receive the signal and continue socket.recv
see cpython socketmodules.c
If the socket function is interrupted by a signal (failed with EINTR): retry
   the function, except if the signal handler raised an exception (PEP 475).

'''





