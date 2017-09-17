"""All Base Classes"""
import atexit
import logging
import os
import time
import sys
from signal import SIGTERM

LOG = logging.getLogger(__name__)


def kill_process(pidfile):
    # Get the pid from the pidfile
    try:
        pf = open(pidfile, 'r')
        pid = int(pf.read().strip())
        pf.close()
    except IOError:
        pid = None

    if not pid:
        message = "pidfile %s does not exist. Daemon not running?\n"
        sys.stderr.write(message % pidfile)
        return  # not an error in a restart

    # Try killing the daemon process
    try:
        while 1:
            os.kill(pid, SIGTERM)
            time.sleep(0.1)
    except OSError as err:
        err = str(err)
        if err.find("No such process") > 0:
            if os.path.exists(pidfile):
                os.remove(pidfile)
        else:
            print(str(err))
            sys.exit(1)


class BaseDaemon(object):

    """
    A generic daemon class.

    Usage: subclass the Daemon class and override the run() method
    Refer: http://web.archive.org/web/20131025230048/http://www.jejik.com/\
    articles/2007/02/a_simple_unix_linux_daemon_in_python/
    """

    def __init__(self, pidfile):
        self.pidfile = pidfile
        sys.stdout = ControlLogger(LOG, logging.INFO)
        sys.stderr = ControlLogger(LOG, logging.ERROR)

    def daemonize(self):
        """
        do the UNIX double-fork magic, see Stevens' "Advanced
        Programming in the UNIX Environment" for details (ISBN 0201563177)
        http://www.erlenstar.demon.co.uk/unix/faq_2.html#SEC16
        """
        try:
            pid = os.fork()
            if pid > 0:
                # exit first parent
                sys.exit(0)
        except OSError as e:
            sys.stderr.write("fork #1 failed: %d (%s)\n" %
                             (e.errno, e.strerror))
            sys.exit(1)

        # decouple from parent environment
        os.chdir("/")
        os.setsid()
        os.umask(0)

        # do second fork
        try:
            pid = os.fork()
            if pid > 0:
                # exit from second parent
                sys.exit(0)
        except OSError as e:
            sys.stderr.write("fork #2 failed: %d (%s)\n" %
                             (e.errno, e.strerror))
            sys.exit(1)

        # write pidfile
        atexit.register(self.delpid)
        pid = str(os.getpid())
        open(self.pidfile, 'w+').write("%s\n" % pid)

    def delpid(self):
        if os.path.exists(self.pidfile):
            os.remove(self.pidfile)

    def status(self):
        try:
            pf = open(self.pidfile, 'r')
            pid = int(pf.read().strip())
            for line in open("/proc/%d/status" % pid).readlines():
                print(line)
        except IOError as e:
            message = 'Unable to open %s pidfile - %s'
            sys.stderr.write(message % (self.pidfile, e))

    def start(self):
        """
        Start the daemon
        """
        # Check for a pidfile to see if the daemon already runs
        try:
            pf = open(self.pidfile, 'r')
            pid = int(pf.read().strip())
            pf.close()
        except IOError:
            pid = None

        if pid:
            message = "pidfile %s already exist. Daemon already running?\n"
            sys.stderr.write(message % self.pidfile)
            sys.exit(1)

        # Start the daemon
        self.daemonize()
        self.run()

    def stop(self):
        """
        Stop the daemon
        """
        kill_process(self.pidfile)

    def restart(self):
        """
        Restart the daemon
        """
        self.stop()
        time.sleep(5)
        self.start()

    def run(self):
        """
        You should override this method when you subclass Daemon.
        It will be called after the process has been
        daemonized by start() or restart().
        """


class ControlLogger(object):

    """
    Fake file-like stream object that redirects writes
    to a logger instance.
    """

    def __init__(self, logger, level):
        self.logger = logger
        self.level = level

    def write(self, message):
        # Only log if there is a message (not just a new line)
        if message.rstrip() != "":
            self.logger.log(self.level, message.rstrip())