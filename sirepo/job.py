# -*- coding: utf-8 -*-
"""Common functionality that is shared between the server, supervisor, and driver.

Because this is going to be shared across the server, supervisor, and driver it
must be py2 compatible.

:copyright: Copyright (c) 2019 RadiaSoft LLC.  All Rights Reserved.
:license: http://www.apache.org/licenses/LICENSE-2.0.html
"""
from __future__ import absolute_import, division, print_function
from pykern import pkconfig
from pykern.pkcollections import PKDict
from pykern.pkdebug import pkdp, pkdc, pkdlog, pkdexc
import sirepo.srdb
import sirepo.util
import re


OP_ANALYSIS = 'analysis'
OP_CANCEL = 'cancel'
OP_ERROR = 'error'
OP_JOB_CMD_STDERR = 'job_cmd_stderr'
OP_KILL = 'kill'
OP_OK = 'ok'
#: Agent indicates it is ready
OP_ALIVE = 'alive'
OP_RUN = 'run'
OP_SBATCH_LOGIN = 'sbatch_login'

#: path supervisor registers to receive messages from agent
AGENT_URI = '/job-agent-websocket'

#: path supervisor registers to receive srtime adjustments from server
SERVER_SRTIME_URI = '/job-api-srtime'

#: path supervisor registers to receive requests from server
SERVER_URI = '/job-api-request'

#: path supervisor registers to receive pings from server
SERVER_PING_URI = '/job-api-ping'

#: path supervisor registers to receive requests from job_process for file PUTs
DATA_FILE_URI = '/job-cmd-data-file'

#: how jobs request files
LIB_FILE_URI = '/job-cmd-lib-file'

#: how jobs request list of files (relative to `LIB_FILE_URI`)
LIB_FILE_LIST_URI = '/list.json'

#: where user lib file directories are linked for static download (job_supervisor)
LIB_FILE_ROOT = None

#: where user data files come in (job_supervisor)
DATA_FILE_ROOT = None

#: how jobs request files (relative to `srdb.root`)
SUPERVISOR_SRV_SUBDIR = 'supervisor-srv'

#: how jobs request files (absolute)
SUPERVISOR_SRV_ROOT = None

#: address where supervisor binds to
DEFAULT_IP = '127.0.0.1'

#: port supervisor is listening on
DEFAULT_PORT = 8001

#: cfg declaration for supervisor_uri for drivers and
DEFAULT_SUPERVISOR_URI_DECL = (
    'http://{}:{}'.format(DEFAULT_IP, DEFAULT_PORT),
    str,
    'how to reach supervisor',
)

#: where runner_api writes simulation state
RUNNER_STATUS_FILE = 'status'

#: status values
CANCELED = 'canceled'
COMPLETED = 'completed'
ERROR = 'error'
FREE_USER_PURGED = 'free_user_purged'
MISSING = 'missing'
PENDING = 'pending'
RUNNING = 'running'

#: When the job is completed
EXIT_STATUSES = frozenset((CANCELED, COMPLETED, ERROR))

#: Valid values for job status
STATUSES = EXIT_STATUSES.union((PENDING, RUNNING))

#: jobRunMode and kinds; should come from schema
SEQUENTIAL = 'sequential'
PARALLEL = 'parallel'
SBATCH = 'sbatch'

#: valid jobRunMode values
RUN_MODES = frozenset((SEQUENTIAL, PARALLEL, SBATCH))

#: categories of jobs
KINDS = frozenset((SEQUENTIAL, PARALLEL))

#: POSIT: Matches anything generated by `unique_key`
UNIQUE_KEY_RE = re.compile(r'^\w+$')

cfg = None

def agent_cmd_stdin_env(cmd, env, pyenv='py3', cwd='.', source_bashrc=''):
    """Convert `cmd` in `pyenv` with `env` to script and cmd

    Uses tempfile so the file can be closed after the subprocess
    gets the handle. You have to close `stdin` after calling
    `tornado.process.Subprocess`, which calls `subprocess.Popen`
    inline, since it' not ``async``.

    Args:
        cmd (iter): list of words to be quoted
        env (str): empty or result of `agent_env`
        pyenv (str): python environment (py3 default)
        cwd (str): directory for the agent to run in (will be created if it doesn't exist)
        uid (str): which user should be logged in

    Returns:
        tuple: new cmd (tuple), stdin (file), env (PKDict)
    """
    import os
    import tempfile

    t = tempfile.TemporaryFile()
    c = 'exec ' + ' '.join(("'{}'".format(x) for x in cmd))
    # POSIT: we control all these values
    t.write(
        '''{}
set -e
mkdir -p '{}'
cd '{}'
pyenv shell {}
{}
{}
'''.format(
        source_bashrc,
        cwd,
        cwd,
        pyenv,
        env or agent_env(),
        c,
    ).encode())
    t.seek(0)
    # it's reasonable to hardwire this path, even though we don't
    # do that with others. We want to make sure the subprocess starts
    # with a clean environment (no $PATH). You have to pass HOME.
    return ('/bin/bash', '-l'), t, PKDict(HOME=os.environ['HOME'])


def agent_env(env=None, uid=None):
    env = (env or PKDict()).pksetdefault(
        **pkconfig.to_environ((
            'pykern.*',
            'sirepo.feature_config.job',
        ))
    ).pksetdefault(
        PYTHONPATH='',
        PYTHONSTARTUP='',
        PYTHONUNBUFFERED='1',
        SIREPO_AUTH_LOGGED_IN_USER=lambda: uid or sirepo.auth.logged_in_user(),
        SIREPO_JOB_VERIFY_TLS=cfg.verify_tls,
        SIREPO_JOB_MAX_MESSAGE_SIZE=cfg.max_message_size,
        SIREPO_JOB_PING_INTERVAL_SECS=cfg.ping_interval_secs,
        SIREPO_JOB_PING_TIMEOUT_SECS=cfg.ping_timeout_secs,
        SIREPO_SRDB_ROOT=lambda: sirepo.srdb.root(),
    )
    return '\n'.join(("export {}='{}'".format(k, v) for k, v in env.items()))


def init():
    global cfg

    cfg = pkconfig.init(
        max_message_size=(int(1e8), int, 'maximum websocket message size'),
        ping_interval_secs=(2*60, int, 'how long to wait between sending keep alive pings'),
        ping_timeout_secs=(4*60, int, 'how long to wait for a ping response'),
        server_secret=(
            'a very secret, secret',
            str,
            'shared secret between supervisor and server',
        ),
        verify_tls=(not pkconfig.channel_in('dev'), bool, 'do not validate (self-signed) certs'),
    )
    global SUPERVISOR_SRV_ROOT, LIB_FILE_ROOT, DATA_FILE_ROOT

    SUPERVISOR_SRV_ROOT = sirepo.srdb.root().join(SUPERVISOR_SRV_SUBDIR)
    LIB_FILE_ROOT = SUPERVISOR_SRV_ROOT.join(LIB_FILE_URI[1:])
    DATA_FILE_ROOT = SUPERVISOR_SRV_ROOT.join(DATA_FILE_URI[1:])


def init_by_server(app):
    """Initialize module"""
    init()

    from sirepo import job_api
    from sirepo import uri_router

    uri_router.register_api_module(job_api)


def supervisor_file_uri(supervisor_uri, *args):
    # trailing slash necessary
    return '{}{}/'.format(supervisor_uri, '/'.join(args))


def unique_key():
    return sirepo.util.random_base62(32)
