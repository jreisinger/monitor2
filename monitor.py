#!/usr/bin/env python
import paramiko
import argparse
import smtplib
from email.mime.text import MIMEText
import getpass
import pickle
import os
import sys

def checks():
    """Checks to be run on remote hosts. Checks output OK or FAIL. run_checks() handles the errors of the checks themselves."""

    checks = {
        # FAIL if ntpd process is not running
        'ntpd':    """ps aux | perl -lne '$found=1 if /\\bntpd\\b/; END { print $found ? "OK" : "FAIL" }'""",

        # FAIL if any partition is used for over 90 %
        'disk':      """df -hP | perl -lne '/^\// or next; ($use,$mount) = (split)[4,5]; push @full, $mount if $use > 90; END { print @full ? "FAIL @full" : "OK" }'""",

        # FAIL if uptime is less than 259 200 seconds (3 days)
        'uptime':    """perl -lane 'print $F[0] > 259_200 ? "OK" : "FAIL"' /proc/uptime""",

        # FAIL if load (last 5 min) is more than 15
        'load':     """perl -lane 'print $F[0] < 15 ? "OK" : "FAIL"' /proc/loadavg"""
    }

    return checks

def parse_args():
    """Parse command line options and arguments"""

    parser = argparse.ArgumentParser(description='Basic monitoring of remote hosts. The output format is HOST | CHECK | STATUS | [INFO]. If there is a problem with a checked feature (CHECK) status is FAIL. If the check itself fails status is ERROR.')
    parser.add_argument('--file', type=argparse.FileType('r'), required=True,
                        help='file containing remote hosts; one host per line',)
    parser.add_argument('--user', type=str, default=getpass.getuser(),
                        help='SSH username; default is the current username',)
    parser.add_argument('--key', type=str,
                        help='SSH private key',)
    parser.add_argument('--port', type=int, default=22,
                        help='SSH network port; default is 22',)
    parser.add_argument('--verbose', action='store_true',
                        help='print what you are doing',)
    parser.add_argument('--mail', action='store_true',
                        help='send failures report via email instead of printing to STDOUT',)
    parser.add_argument('--nocheck', nargs='+',
                        help='do not run these checks',)

    return parser.parse_args()

class Checks():
    def __init__(self, hosts, emails=[]):
        self.hosts = hosts
        self.emails = emails
        self.fails = []

    def run(self):
        """Execute checks on hosts."""

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.load_system_host_keys()

        for host in self.hosts:
            try:
                ssh.connect(host, parse_args().port, parse_args().user, key_filename=parse_args().key)
            except Exception as e:
                self.fails.append( { 'host': host, 'check': 'SSH', 'status': 'ERROR', 'msg': str(e) } )
                continue # like Perl's next()

            for name, cmd in checks().iteritems():

                # skip some checks defined on the commandline?
                if parse_args().nocheck and filter(lambda check: name == check, parse_args().nocheck):
                    continue

                stdin, stdout, stderr = ssh.exec_command(cmd)

                # if the check itself fails it outputs ERROR
                err = stderr.read().rstrip()
                if err:
                    if args.verbose:
                        print " | ".join([ host, name, 'ERROR', err ])
                    self.fails.append( { 'host': host, 'check': name, 'status': 'ERROR', 'msg': err } )
                    continue  # like next in Perl

                output = stdout.read().rstrip()
                words = output.split()
                status = words[0]
                msg = "".join(words[1:])
                if args.verbose:
                    print " | ".join([ host, name, status, msg ])
                if status != 'OK':
                    self.fails.append( { 'host': host, 'check': name, 'status': status, 'msg': msg } )

            ssh.close()

    def print_failures(self):
        print(self._format_fails(self.fails))

    def email_failures(self, emails):
        """If we have some failed checks send them via email"""

        sender = 'monitor'
        recipients = emails
        subject = 'system monitor'

        body = self._format_fails(self.fails)

        if not body:
            return

        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = sender
        msg['To'] = ", ".join(recipients)
        try:
            s = smtplib.SMTP('localhost')
        except Exception as e:
            sys.stderr.write("Can't connect to localhost for sending email: " + str(e) + "\n")
            exit(1)
        s.sendmail(sender, recipients, msg.as_string())
        s.quit()

    def _format_fails(self, fails):
        """Prepare info about fails to be printed out or emailed"""

        output = "\n---\n"
        for item in fails:
            output = output + " | ".join([item['host'], item['check'], item['status'], item['msg']]) + "\n"
        output += "---\n"

        return output

    def seen(self, filename):
        """Have we already seen these fails?"""

        hosts_file = os.path.splitext(os.path.basename(filename))[0]
        data_file = ".".join( [ "monitor", hosts_file, "data" ] )

        seen = False

        if os.path.isfile(data_file):
            prev_fails = pickle.load( open( data_file, "rb" ) )
            if self.fails == prev_fails:
                seen = True
        pickle.dump( self.fails, open( data_file, "wb" ) )

        return seen

if __name__ == "__main__":
    args = parse_args()

    hosts = args.file.read().splitlines()   # remove newlines

    check = Checks(hosts)
    check.run()

    if args.mail and check.seen(args.file.name):
        check.email_failures([ 'jane.doe@example.com', 'john.smith@example.org' ])
    else:
        if check.seen(args.file.name):
            print "NOTE: we've already seen these fails"
        check.print_failures()
