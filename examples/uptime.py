from dollybot import *
import sys
import subprocess
import argparse

class UptimeBot(DollyBot):
    
    def __init__(self, jid, password, domain, muc_domain):
        super(UptimeBot, self).__init__(jid, password)

        self.domain = domain
        self.muc_domain = muc_domain

    @botcmd
    def uptime(self, msg, args):
        return subprocess.check_output(["uptime"])

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="UptimeBot")

    parser.add_argument("-u", "--username", dest="username", action="store", type=str, required=True, help="Your username")
    parser.add_argument("-p", "--password", dest="password", action="store", type=str, required=True, help="Your password")
    parser.add_argument("-d", "--domain", dest="domain", action="store", type=str, required=True, help="the domain")
    parser.add_argument("-c", "--muc_domain", dest="muc_domain", action="store", type=str, required=True, help="the conference domain")
    args = parser.parse_args()

    bot = UptimeBot(args.username, args.password, args.domain, args.muc_domain)
    bot.serve_forever()
