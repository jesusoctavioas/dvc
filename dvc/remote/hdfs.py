import os
import re
import getpass
import posixpath
from subprocess import Popen, PIPE

try:
    from urlparse import urlparse
except ImportError:
    from urllib.parse import urlparse

from dvc.config import Config
from dvc.remote.base import RemoteBase
from dvc.exceptions import DvcException


class RemoteHDFS(RemoteBase):
    scheme='hdfs'
    REGEX = r'^hdfs://((?P<user>.*)@)?.*$'
    PARAM_CHECKSUM = 'checksum'

    def __init__(self, project, config):
        self.project = project
        self.url = config.get(Config.SECTION_REMOTE_URL, '/')
        self.user = self.group('user')
        if not self.user:
            self.user = config.get(Config.SECTION_REMOTE_USER, getpass.getuser())

    def hadoop_fs(self, cmd, user=None):
        cmd = 'hadoop fs -' + cmd
        if user:
            cmd = 'HADOOP_USER_NAME={} '.format(user) + cmd
        p = Popen(cmd,
                  shell=True,
                  close_fds=True,
                  executable=os.getenv('SHELL'),
                  stdin=PIPE,
                  stdout=PIPE,
                  stderr=PIPE)
        out, err = p.communicate()
        if p.returncode != 0:
            raise DvcException('HDFS command failed: {}: {}'.format(cmd, err))
        return out.decode('utf-8')

    @staticmethod
    def _group(regex, s, gname):
        match = re.match(regex, s)
        assert match != None
        return match.group(gname)

    def checksum(self, path_info):
        regex = r'.*\t.*\t(?P<checksum>.*)'
        stdout = self.hadoop_fs('checksum {}'.format(path_info['url']), user=path_info['user'])
        return self._group(regex, stdout, 'checksum')

    def cp(self, from_info, to_info):
        self.hadoop_fs('mkdir -p {}'.format(posixpath.dirname(to_info['url'])), user=to_info['user'])
        self.hadoop_fs('cp {} {}'.format(from_info['url'], to_info['url']), user=to_info['user'])

    def rm(self, path_info):
        self.hadoop_fs('rm {}'.format(path_info['url']), user=path_info['user'])

    def save_info(self, path_info):
        if path_info['scheme'] != 'hdfs':
            raise NotImplementedError

        assert path_info.get('url')

        return {self.PARAM_CHECKSUM: self.checksum(path_info)}

    def save(self, path_info):
        if path_info['scheme'] != 'hdfs':
            raise NotImplementedError

        assert path_info.get('url')

        checksum = self.checksum(path_info)
        dest = path_info.copy()
        dest['url'] = posixpath.join(self.url, checksum[0:2], checksum[2:])

        self.cp(path_info, dest)

        return {self.PARAM_CHECKSUM: checksum}

    def checkout(self, path_info, checksum_info):
        if path_info['scheme'] != 'hdfs':
            raise NotImplementedError

        assert path_info.get('url')

        checksum = checksum_info.get(self.PARAM_CHECKSUM, None)
        if not checksum:
            return

        src = path_info.copy()
        src['url'] = posixpath.join(self.url, checksum[0:2], checksum[2:])

        self.cp(src, path_info)

    def remove(self, path_info):
        if path_info['scheme'] != 'hdfs':
            raise NotImplementedError

        assert path_info.get('url')

        self.rm(path_info)

    def upload(self, path, path_info):
        if path_info['scheme'] != 'hdfs':
            raise NotImplementedError

        self.hadoop_fs('mkdir -p {}'.format(posixpath.dirname(path_info['url'])), user=path_info['user'])
        self.hadoop_fs('copyFromLocal {} {}'.format(path, path_info['url']), user=path_info['user'])

    def download(self, path_info, path):
        if path_info['scheme'] != 'hdfs':
            raise NotImplementedError

        dname = os.path.dirname(path)
        if not os.path.exists(dname):
            os.makedirs(dname)

        self.hadoop_fs('copyToLocal {} {}'.format(path_info['url'], path), user=path_info['user'])
