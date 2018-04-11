# Copyright 2017-2018 TensorHub, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import struct
import sys
import threading
import time

import yaml

import guild.run
from guild import util

class RunOutput(object):

    DEFAULT_WAIT_TIMEOUT = 10

    def __init__(self, run, proc=None, quiet=False):
        assert run
        self._run = run
        self._quiet = quiet
        self._output_lock = threading.Lock()
        self._open = False
        self._proc = None
        self._output = None
        self._index = None
        self._out_tee = None
        self._err_tee = None
        if proc:
            self.open(proc)

    @property
    def closed(self):
        return not self._open

    def open(self, proc):
        self._assert_closed()
        if proc.stdout is None:
            raise RuntimeError("proc stdout must be a PIPE")
        if proc.stderr is None:
            raise RuntimeError("proc stderr must be a PIPE")
        self._proc = proc
        self._output = self._open_output()
        self._index = self._open_index()
        self._out_tee = threading.Thread(target=self._out_tee_run)
        self._err_tee = threading.Thread(target=self._err_tee_run)
        self._out_tee.start()
        self._err_tee.start()
        self._open = True

    def _assert_closed(self):
        if self._open:
            raise RuntimeError("already open")
        assert self._proc is None
        assert self._output is None
        assert self._index is None
        assert self._out_tee is None
        assert self._err_tee is None

    def _open_output(self, mode="w"):
        path = self._run.guild_path("output")
        return open(path, mode + "b")

    def _open_index(self, mode="w"):
        path = self._run.guild_path("output.index")
        return open(path, mode + "b")

    def _out_tee_run(self):
        assert self._proc
        self._gen_tee_run(self._proc.stdout, sys.stdout, 0)

    def _err_tee_run(self):
        assert self._proc
        self._gen_tee_run(self._proc.stderr, sys.stderr, 1)

    def _gen_tee_run(self, input_stream, output_stream, stream_type):
        assert self._output
        assert self._index
        os_read = os.read
        os_write = os.write
        input_fileno = input_stream.fileno()
        if not self._quiet:
            stream_fileno = output_stream.fileno()
        else:
            stream_fileno = None
        output_fileno = self._output.fileno()
        index_fileno = self._index.fileno()
        time_ = time.time
        lock = self._output_lock
        line = []
        while True:
            b = os_read(input_fileno, 1)
            if not b:
                break
            with lock:
                if stream_fileno is not None:
                    os_write(stream_fileno, b)
                line.append(b)
                if b == b"\n":
                    os_write(output_fileno, b"".join(line))
                    line = []
                    entry = struct.pack(
                        "!QB", int(time_() * 1000), stream_type)
                    os_write(index_fileno, entry)

    def wait(self, timeout=DEFAULT_WAIT_TIMEOUT):
        self._assert_open()
        self._out_tee.join(timeout)
        self._err_tee.join(timeout)

    def _assert_open(self):
        if not self._open:
            raise RuntimeError("not open")
        assert self._proc
        assert self._output
        assert self._index
        assert self._out_tee
        assert self._err_tee

    def close(self):
        self._assert_open()
        self._output.close()
        self._index.close()
        assert not self._out_tee.is_alive()
        assert not self._err_tee.is_alive()
        self._proc = None
        self._output = None
        self._index = None
        self._out_tee = None
        self._err_tee = None
        self._open = False

    def wait_and_close(self, timeout=DEFAULT_WAIT_TIMEOUT):
        self.wait(timeout)
        self.close()

    def __iter__(self):
        with self._output_lock:
            output = self._open_output("r")
            index = self._open_index("r")
            for line in output:
                time, stream = struct.unpack("!QB", index.read(9))
                yield time, stream, line

def resolve_file(filename):
    return util.find_apply([
        _abs_file,
        _cmd_file,
        _model_file,
        _cwd_file
    ], filename)

def _abs_file(filename):
    if os.path.isabs(filename):
        return filename
    return None

def _cmd_file(filename):
    assert "CMD_DIR" in os.environ
    filename = os.path.join(os.environ["CMD_DIR"], filename)
    if os.path.exists(filename):
        return filename
    return None

def _model_file(filename):
    assert "MODEL_DIR" in os.environ
    filename = os.path.join(os.environ["MODEL_DIR"], filename)
    if os.path.exists(filename):
        return filename
    return None

def _cwd_file(filename):
    return os.path.join(os.getcwd(), filename)

def parse_args(args):
    return dict([_parse_arg(os.path.expanduser(arg)) for arg in args])

def _parse_arg(s):
    parts = s.split("=", 1)
    if len(parts) == 1:
        return parts[0], None
    else:
        return parts[0], _parse_arg_val(parts[1])

def _parse_arg_val(s):
    try:
        return yaml.safe_load(s)
    except yaml.YAMLError:
        return s

class NoCurrentRun(Exception):
    pass

def current_run():
    """Returns an instance of guild.run.Run for the current run.

    The current run directory must be specified with the RUN_DIR
    environment variable. If this variable is not defined, raised
    NoCurrentRun.

    """
    path = os.getenv("RUN_DIR")
    if not path:
        raise NoCurrentRun()
    return guild.run.Run(os.getenv("RUN_ID"), path)

class TFEvents(object):

    def __init__(self, logdir):
        self.logdir = logdir
        self._writer = None

    def add_scalars(self, scalars, global_step=None):
        self._ensure_writer()
        self._writer.add_summary(self._scalars_summary(scalars), global_step)

    @staticmethod
    def _scalars_summary(scalars):
        import tensorflow as tf
        value = [
            tf.summary.Summary.Value(tag=tag, simple_value=val)
            for tag, val in scalars
        ]
        return tf.summary.Summary(value=value)

    def _ensure_writer(self):
        import tensorflow as tf
        if not self._writer:
            self._writer = tf.summary.FileWriter(self.logdir, max_queue=0)

    def close(self):
        if self._writer:
            self._writer.close()
            self._writer = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

def tfevents(subdir=None, run=None):
    if not run:
        run = current_run()
    if subdir:
        logdir = os.path.join(run.path, subdir)
    else:
        logdir = run.path
    return TFEvents(logdir)
