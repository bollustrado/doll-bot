#!/usr/bin/python
# -*- coding: utf-8 -*-

# JabberBot: A simple jabber/xmpp bot framework
# Copyright (c) 2007-2012 Thomas Perl <thp.io/about>
# $Id: 25a112d76ea21c75e4234f00baf4038d92efe329 $
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

"""
A framework for writing Jabber/XMPP bots and services

The JabberBot framework allows you to easily write bots
that use the XMPP protocol. You can create commands by
decorating functions in your subclass or customize the
bot's operation completely. MUCs are also supported.
"""

import os
import re
import sys
import threading

try:
    import sleekxmpp
except ImportError:
    print >> sys.stderr, """
    You need to install sleekxmpp from http://sleekxmpp.com/.
    """
    sys.exit(-1)

import time
import inspect
import logging
import traceback

# Will be parsed by setup.py to determine package metadata
__author__ = 'Thomas Perl <m@thp.io>'
__version__ = '0.15'
__website__ = 'http://thp.io/2007/python-jabberbot/'
__license__ = 'GNU General Public License version 3 or later'

def botcmd(*args, **kwargs):
    """Decorator for bot command functions"""

    def decorate(func, hidden=False, admin=False, name=None, thread=False):
        setattr(func, '_jabberbot_command', True)
        setattr(func, '_jabberbot_command_hidden', hidden)
        setattr(func, '_jabberbot_command_admin', admin)
        setattr(func, '_jabberbot_command_name', name or func.__name__)
        setattr(func, '_jabberbot_command_thread', thread)  # Experimental!
        return func

    if len(args):
        return decorate(args[0], **kwargs)
    else:
        return lambda func: decorate(func, **kwargs)


class JabberBot(object):

    def __init__(self, username, password, res=None, debug=False,
            privatedomain=False, acceptownmsgs=False, handlers=None,
            plugins=None, command_prefix=''):
        
        """Initializes the jabber bot and sets up commands.

        username and password should be clear ;)

        If res provided, res will be ressourcename,
        otherwise it defaults to classname of childclass

        If debug is True log messages of xmpppy will be printed to console.
        Logging of Jabberbot itself is NOT affected.

        If privaedomain is provided, it should be either
        True to only allow subscriptions from the same domain
        as the bot or a string that describes the domain for
        which subscriptions are accepted (e.g. 'jabber.org').

        If acceptownmsgs it set to True, this bot will accept
        messages from the same JID that the bot itself has. This
        is useful when using JabberBot with a single Jabber account
        and multiple instances that want to talk to each other.

        If handlers are provided, default handlers won't be enabled.
        Usage like: [('stanzatype1', function1), ('stanzatype2', function2)]
        Signature of function should be callback_xx(self, conn, stanza),
        where conn is the connection and stanza the current stanza in process.
        First handler in list will be served first.
        Don't forget to raise exception xmpp.NodeProcessed to stop
        processing in other handlers (see callback_presence)

        If command_prefix is set to a string different from '' (the empty
        string), it will require the commands to be prefixed with this text,
        e.g. command_prefix = '!' means: Type "!info" for the "info" command.
        """

        # CHECK WHAT IS ACCUTALY USED!

        # TODO sort this initialisation thematically
        self.__debug = debug
        
        logging.basicConfig(filename='jabberbot.log', level=logging.INFO)
        self.log = logging.getLogger(__name__)
        self.nick = ""
        self.__username = username
        self.jid = self.__username 
        self.__password = password
        self.xmpp = sleekxmpp.ClientXMPP(self.__username, self.__password);
        self.res = (res or self.__class__.__name__)
        self.conn = None
        self.__privatedomain = privatedomain
        self.__command_prefix = command_prefix

        # Define the plugins for xmpp
        self.plugins = (plugins or [('xep_0030'),
                                    ('xep_0045'),
                                    ('xep_0199')])

        # Define the handlers for xmpp events
        self.handlers = (handlers or [('session_start', self.start),
                                    ('message', self.message_callback),
                                    ('groupchat_message', self.muc_message_callback)])

        # Set the plugins and handlers
        self.xmpp_config()

        # Collect commands from source
        self.commands = {}
        for name, value in inspect.getmembers(self, inspect.ismethod):
            if getattr(value, '_jabberbot_command', False):
                name = getattr(value, '_jabberbot_command_name')
                self.log.info('Registered command: %s' % name)
                self.commands[self.__command_prefix + name] = value
        
        self.roster = None
    
    def xmpp_config(self):
        """Configure the xmpp"""
        self.log.info("Configuring the xmpp")
        
        for plugin in self.plugins:
            self.xmpp.register_plugin(plugin)
            self.log.info("Registered plugin: %s" % plugin)

        for (handler, callback) in self.handlers:
            self.xmpp.add_event_handler(handler, callback)
            self.log.info("Registered handler: %s" % handler)

    def start(self, event):
        """Process the session_start event."""
 
        # Send initial presence stanza (say hello to everyone)
        self.xmpp.send_presence()
        
        # Save roster and log Items
        try:
            self.roster = self.xmpp.get_roster()
            self.log.info("self.roster")
        except IqError as err:
            self.log.error("Error: %" % err.iq['error']['condition'])
        except IqTimeout:
            self.log.error("Error: Request timed out");
        self.xmpp.send_presence()

        #self.xmpp.presences_received.wait(5)
        
        """
        for contact in self.roster.getItems():
            self.log.info('  %s' % contact)
        self.log.info('*** roster ***')
        """

        self.on_login()

    def on_login(self):
        """This function will be called when we're logged in

        Override this method in derived class if you
        want to do anything special at login.
        """
        pass

    def send_mucm(self, to, msg):
        self.xmpp.send_message(mto="%s@%s" % (to, self.muc_domain),
                                mbody="%s" % msg,
                                mtype="groupchat")

    def send_pm(self, to, msg):
        self.xmpp.send_message(mto="%s@%s" % (to, self.domain),
                               mbody="%s" % msg,
                               mtype="chat")
 
    def muc_message_callback(self, msg):
        if msg['type'] not in ('groupchat'):
            return
        
        if msg['mucnick'] != self.nick and self.nick in msg['body']:
            args = ""
            reply = self.unknown_command(msg, args)
            msg.reply("%s" % reply).send()

    def message_callback(self, msg):
        if msg['type'] not in ('chat', 'normal'):
            return
        
        cmd = ""
        args = ""
        command = ""
        text = msg['body']
        is_command = False

        if text.startswith('!'):
            is_command = True

        if is_command and ' ' in text:
            cmd, args = text.split(' ', 1)
        else:
            cmd = text
            
        cmd = cmd[1:]

        cmd = cmd.lower()
        self.log.info("*** cmd = %s" % cmd)
 
        # Ignore messages from myself
        if self.jid == msg['from'].bare:
            return None

        if cmd in self.commands:
            try:
                reply = self.commands[cmd](msg, args)
            except Exception as e:
                self.log.exception('An error happened while processing '\
                    'a message ("%s") from %s: %s"' %
                    (text, self.jid, "prutt"))
                reply = self.MSG_ERROR_OCCURRED
        else:
            reply = self.unknown_command(msg, args)

        msg.reply("%s" % reply).send()

    def unknown_command(self, msg, cmd, args):
        """Default handler for unknown commands

        Override this method in derived class if you
        want to trap some unrecognized commands.  If
        'cmd' is handled, you must return some non-false
        value, else some helpful text will be sent back
        to the sender.
        """
        return None

    def top_of_help_message(self):
        """Returns a string that forms the top of the help message

        Override this method in derived class if you
        want to add additional help text at the
        beginning of the help message.
        """
        return ""

    def bottom_of_help_message(self):
        """Returns a string that forms the bottom of the help message

        Override this method in derived class if you
        want to add additional help text at the end
        of the help message.
        """
        return ""

    @botcmd
    def help(self, mess, args):
        """   Returns a help string listing available options.

        Automatically assigned to the "help" command."""
        if not args:
            if self.__doc__:
                description = self.__doc__.strip()
            else:
                description = 'Available commands:'

            usage = '\n'.join(sorted([
                '%s: %s' % (name, (command.__doc__ or \
                    '(undocumented)').strip().split('\n', 1)[0])
                for (name, command) in self.commands.items() \
                    if name != (self.__command_prefix + 'help') \
                    and not command._jabberbot_command_hidden
            ]))
            usage = '\n\n' + '\n\n'.join(filter(None,
                [usage, self.MSG_HELP_TAIL % {'helpcommand':
                    self.__command_prefix + 'help'}]))
        else:
            description = ''
            if (args not in self.commands and
                    (self.__command_prefix + args) in self.commands):
                # Automatically add prefix if it's missing
                args = self.__command_prefix + args
            if args in self.commands:
                usage = (self.commands[args].__doc__ or \
                    'undocumented').strip()
            else:
                usage = self.MSG_HELP_UNDEFINED_COMMAND

        top = self.top_of_help_message()
        bottom = self.bottom_of_help_message()
        return ''.join(filter(None, [top, description, usage, bottom]))

##################################################3

    def shutdown(self):
        """This function will be called when we're done serving

        Override this method in derived class if you
        want to do anything special at shutdown.
        """
        pass
 
    def quit(self):
        """Stop serving messages and exit."""

        self.log.warn('committing sueside!')
        self.xmpp.disconnect()
        exit(0)

    def serve_forever(self, connect_callback=None, disconnect_callback=None):
        """Connects to the server and handles messages."""
        
        #self.xmpp.add_event_handler("session_start", self.start)
        
        conn = self.xmpp.connect()
       
        if conn:
            self.log.info('bot connected. serving forever.')
        else:
            self.log.warn('could not connect to server - aborting.')
            return
        
        if connect_callback:
            connect_callback()
        
        # This way the bot will die on disconnect..
        # or will it?
        self.xmpp.process(block=True)
       
        self.shutdown()
        
        if disconnect_callback:
            disconnect_callback()

# vim: expandtab tabstop=4 shiftwidth=4 softtabstop=4
