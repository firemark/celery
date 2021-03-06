# -*- coding: utf-8 -*-
"""Program used to daemonize the worker.

Using :func:`os.execv` as forking and multiprocessing
leads to weird issues (it was a long time ago now, but it
could have something to do with the threading mutex bug)
"""
from __future__ import absolute_import, unicode_literals

import celery
import os
import sys

from optparse import OptionParser, BadOptionError

from celery.platforms import EX_FAILURE, detached
from celery.utils.log import get_logger
from celery.utils.nodenames import default_nodename, node_format

from celery.bin.base import daemon_options

__all__ = ['detached_celeryd', 'detach']

logger = get_logger(__name__)

C_FAKEFORK = os.environ.get('C_FAKEFORK')


def detach(path, argv, logfile=None, pidfile=None, uid=None,
           gid=None, umask=None, working_directory=None, fake=False, app=None,
           executable=None, hostname=None):
    hostname = default_nodename(hostname)
    logfile = node_format(logfile, hostname)
    pidfile = node_format(pidfile, hostname)
    fake = 1 if C_FAKEFORK else fake
    with detached(logfile, pidfile, uid, gid, umask, working_directory, fake,
                  after_forkers=False):
        try:
            if executable is not None:
                path = executable
            os.execv(path, [path] + argv)
        except Exception:
            if app is None:
                from celery import current_app
                app = current_app
            app.log.setup_logging_subsystem(
                'ERROR', logfile, hostname=hostname)
            logger.critical("Can't exec %r", ' '.join([path] + argv),
                            exc_info=True)
        return EX_FAILURE


class PartialOptionParser(OptionParser):

    def __init__(self, *args, **kwargs):
        self.leftovers = []
        OptionParser.__init__(self, *args, **kwargs)

    def _process_long_opt(self, rargs, values):
        arg = rargs.pop(0)

        if '=' in arg:
            opt, next_arg = arg.split('=', 1)
            rargs.insert(0, next_arg)
            had_explicit_value = True
        else:
            opt = arg
            had_explicit_value = False

        try:
            opt = self._match_long_opt(opt)
            option = self._long_opt.get(opt)
        except BadOptionError:
            option = None

        if option:
            if option.takes_value():
                nargs = option.nargs
                if len(rargs) < nargs:
                    if nargs == 1:
                        self.error('{0} requires an argument'.format(opt))
                    else:
                        self.error('{0} requires {1} arguments'.format(
                            opt, nargs))
                elif nargs == 1:
                    value = rargs.pop(0)
                else:
                    value = tuple(rargs[0:nargs])
                    del rargs[0:nargs]

            elif had_explicit_value:
                self.error('{0} option does not take a value'.format(opt))
            else:
                value = None
            option.process(opt, value, values, self)
        else:
            self.leftovers.append(arg)

    def _process_short_opts(self, rargs, values):
        arg = rargs[0]
        try:
            OptionParser._process_short_opts(self, rargs, values)
        except BadOptionError:
            self.leftovers.append(arg)
            if rargs and not rargs[0][0] == '-':
                self.leftovers.append(rargs.pop(0))


class detached_celeryd(object):
    usage = '%prog [options] [celeryd options]'
    version = celery.VERSION_BANNER
    description = ('Detaches Celery worker nodes.  See `celery worker --help` '
                   'for the list of supported worker arguments.')
    command = sys.executable
    execv_path = sys.executable
    execv_argv = ['-m', 'celery', 'worker']

    def __init__(self, app=None):
        self.app = app

    def create_parser(self, prog_name):
        p = PartialOptionParser(
            prog=prog_name,
            usage=self.usage,
            description=self.description,
            version=self.version,
        )
        self.prepare_arguments(p)
        return p

    def parse_options(self, prog_name, argv):
        parser = self.create_parser(prog_name)
        options, values = parser.parse_args(argv)
        if options.logfile:
            parser.leftovers.append('--logfile={0}'.format(options.logfile))
        if options.pidfile:
            parser.leftovers.append('--pidfile={0}'.format(options.pidfile))
        if options.hostname:
            parser.leftovers.append('--hostname={0}'.format(options.hostname))
        return options, values, parser.leftovers

    def execute_from_commandline(self, argv=None):
        argv = sys.argv if argv is None else argv
        config = []
        seen_cargs = 0
        for arg in argv:
            if seen_cargs:
                config.append(arg)
            else:
                if arg == '--':
                    seen_cargs = 1
                    config.append(arg)
        prog_name = os.path.basename(argv[0])
        options, values, leftovers = self.parse_options(prog_name, argv[1:])
        sys.exit(detach(
            app=self.app, path=self.execv_path,
            argv=self.execv_argv + leftovers + config,
            **vars(options)
        ))

    def prepare_arguments(self, parser):
        daemon_options(parser, default_pidfile='celeryd.pid')
        parser.add_option('--workdir', default=None, dest='working_directory')
        parser.add_option('-n', '--hostname')
        parser.add_option(
            '--fake',
            default=False, action='store_true', dest='fake',
            help="Don't fork (for debugging purposes)",
        )


def main(app=None):
    detached_celeryd(app).execute_from_commandline()

if __name__ == '__main__':  # pragma: no cover
    main()
