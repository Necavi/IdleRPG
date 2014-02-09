import threading
import socket
import time
import traceback
import sys

from . import event
from datetime import datetime
from collections import deque


class NickClass:
    def __init__(self, nick, host):
        self.nick = nick
        self.host = host
        
    def __repr__(self):
        return self.nick
        
    def __str__(self):
        return self.nick
        
    def __eq__(self, other):
        if isinstance(other, str):
            return self.nick == other
        else:
            return super(object, self).__eq__(other)


class IRCEvents:
    def __init__(self):
        self.connected = event.Event()
        self.msg = event.Event()
        self.chanmsg = event.Event()
        self.privmsg = event.Event()
        self.join = event.Event()
        self.part = event.Event()
        self.quit = event.Event()
        self.nick = event.Event()
        self.ctcp = event.Event()
        self.raw = event.Event()
        self.numeric = event.Event()

    def connected(self):
        self.connected()

    def msg(self, target, message):
        self.msg(target, message)

    def chanmsg(self, channel, nick, message):
        self.chanmsg(channel, nick, message)

    def privmsg(self, nick, message):
        self.privmsg(nick, message)

    def join(self, channel, nick):
        self.join(channel, nick)

    def part(self, channel, nick):
        self.part(channel, nick)

    def quit(self, channel, nick):
        self.quit(channel, nick)

    def nick(self, oldnick, newnick):
        self.nick(oldnick, newnick)
    
    def ctcp(self, source, nick, num, message):
        self.ctcp(source, nick, num, message)
        
    def raw(self, message):
        self.raw(message)
    
    def numeric(self, number, message):
        self.numeric(number, message)


class Bot:
    def __init__(self, connection, nick, usessl=False):
        self.recv_thread = threading.Thread(target=self.recvmgr, name="receive-thread")
        self.send_thread = threading.Thread(target=self.sendmgr, name="send-thread")
        self.ircevents = IRCEvents()
        self.messagequeue = deque()
        if sys.__stdout__ is None:
            self.stdout = sys.stdout
        else:
            self.stdout = sys.__stdout__
        self.connection = connection
        self.tsocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if usessl:
            try:
                import ssl
            except ImportError:
                self.print("Unable to initiate SSL for this server")
            else:
                self.tsocket = ssl.wrap_socket(self.tsocket)
        self.tsocket.connect(self.connection)
        self.fsocket = self.tsocket.makefile()
        self.nick = nick
        self.print(self.tsocket)
        self.sendmsg("NICK {}".format(self.nick))
        self.sendmsg("USER {0} {0} {0} :{0}".format(self.nick))
        self.recv_thread.start()
        self.send_thread.start()
        
    def join(self, channel):
        message = "JOIN " + channel
        self.sendmsg(message)
        message = "WHO " + channel
        self.sendmsg(message)

    def part(self, channel, message=""):
        self.print(message)
        message = "PART {} :{}".format(channel, message)
        self.sendmsg(message)

    def action(self, target, message):
        message = "PRIVMSG {} :\x01ACTION {}\x01".format(target, message)
        self.sendmsg(message)

    def msg(self, target, message):
        message = "PRIVMSG {} :{}".format(target, message)
        self.sendmsg(message)

    def notice(self, target, message):
        message = "NOTICE {} :{}".format(target, message)
        self.sendmsg(message)

    def mode(self, channel, mode, message):
        message = "MODE {} {} {}".format(channel, mode, message)
        self.sendmsg(message)
    
    def sendmsg(self, message):
        self.messagequeue.appendleft(message)

    def sendmgr(self):
        while True:
            if len(self.messagequeue) > 0:
                message = self.messagequeue.pop()
                if len(message) > 510:
                    split = message.split(" ")
                    message2 = "{} {} {}".format(split[0],split[1],message[:510])
                    message = message[510:]
                    self.messagequeue.appendleft(message2)
                self.print(message)
                try:
                    self.tsocket.send(bytes(message + "\r\n", "utf-8"))
                except OSError:
                    self.printerr(traceback.format_exc())
            time.sleep(0.5)

    def print(self, message):
        curtime = datetime.now().replace(microsecond=0)
        self.stdout.write("[{}] {}\n".format(curtime, message))

    def printerr(self, message):
        curtime = datetime.now().replace(microsecond=0)
        sys.stderr.write("[{}] {}\n".format(curtime, message))

    def parsemessage(self, message):
        self.ircevents.raw(message)
        command = message.split(" ")
        if command[0] == "PING":
            message = "PONG " + command[1]
            self.sendmsg(message)
        elif command[1] == "PRIVMSG" or command[1] == "NOTICE":
            if command[3].lstrip(":").startswith("\x01") and command[3].lstrip(":").endswith("\x01"):
                self.ircevents.ctcp(command[2], self.parsename(command[0]), command[3].lstrip(":").strip("\x01"),
                                    " ".join(command[4:]))
            else:
                message = command[3].lstrip(":") + " " + " ".join(command[4:])
                nick = self.parsename(command[0])
                self.ircevents.msg(nick, message)
                if command[2].startswith("#"):
                    self.ircevents.chanmsg(command[2], nick, message)
                elif command[2] == self.nick:
                    self.ircevents.privmsg(nick, message)
        elif command[1].isnumeric():
            self.ircevents.numeric(int(command[1]), " ".join(command[2:]))
            if command[1] == "001":
                self.ircevents.connected()
        elif command[1] == "JOIN":
            nick = self.striptags(self.parsename(command[0]))
            self.ircevents.join(command[2], nick)
        elif command[1] == "PART":
            nick = self.parsename(command[0])
            self.ircevents.part(command[2], nick)
        elif command[1] == "QUIT":
            nick = self.parsename(command[0])
            self.ircevents.quit(command[2], nick)
        elif command[1] == "NICK":
            self.ircevents.nick(self.parsename(command[0]), self.parsename(command[2]))
            
    def striptags(self, name):
        name.nick = name.nick.lstrip("@+:")
        return name

    def parsename(self, name):
        nick, ban, identhost = name.partition("!")
        nick = nick.lstrip(":")
        return NickClass(nick, name)

    def recvmgr(self):
        while True:
            try:
                data = self.fsocket.readline().rstrip("\r\n")
                if not data:
                    time.sleep(0.1)
                    break
                self.print(data)
                self.parsemessage(data)
            except OSError:
                self.printerr(traceback.print_exc())
            time.sleep(0.01)
