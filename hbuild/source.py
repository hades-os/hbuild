import os
import subprocess

from enum import Enum
from functools import partial

from .step import Step

import git
from git import RemoteProgress

import pathlib
import shutil

import tarfile
from tarfile import TarInfo

from rich.progress import Progress
from rich import print as rich_print

from subprocess import CalledProcessError

from urllib.parse import urlparse
from urllib.request import urlopen

class SourceType(Enum):
    URL = 1
    GIT = 2

class CloneType(Enum):
    COMMIT = 0
    BRANCH = 1
    TAG = 2

class CloneProgress(RemoteProgress):
    def __init__(self, progress: Progress):
        super().__init__()

        self.progress = progress

        self.clone_bar = self.progress.add_task("[cyan] Cloning...", total = None)
        self.set_total = False

        self.cur_count = 0

    def update(self, op_code, cur_count, max_count = None, message = ''):
        if max_count and self.set_total is False:
            self.progress.update(self.clone_bar, total = max_count)
            self.set_total = True

        prev_count = self.cur_count

        self.cur_count = cur_count
        self.progress.update(self.clone_bar, advance = self.cur_count - prev_count)

class DownloadProgress:
    def __init__(self, url, dir, progress: Progress):
        self.url = url
        self.dir = dir

        self.progress = progress

        self.parsed_url = urlparse(self.url)
        self.file = os.path.basename(self.parsed_url.path)

        self.output_path = os.path.join(self.dir, self.file)

    def acquire(self):
        download_bar = self.progress.add_task("[cyan] Downloading...", total = None)

        with urlopen(self.url) as res:
            res.getheaders()

            content_length = res.getheader("Content-Length")
            if content_length is not None:
                self.progress.update(download_bar, total = int(content_length))

            with open(self.output_path, "wb") as output_file:
                self.progress.start_task(download_bar)
                for data in iter(partial(res.read, 32768), b""):
                    output_file.write(data)
                    self.progress.update(download_bar, advance = len(data))

# sources_dir, system_dir, system_prefix, system_targets
class SourcePackage:
    def __init__(self, source_data, sources_dir, patches_dir, system_targets, system_prefix, system_root):
        source_properties = source_data

        self.name = source_properties["name"]

        if "subdir" in source_properties:
            self.subdir = source_properties["subdir"]
            self.dir = os.path.join(self.subdir, self.name)
        else:
            self.dir = self.name
        
        self.patches_dir = patches_dir
        self.sources_dir = sources_dir
        self.system_prefix = system_prefix
        self.system_targets = system_targets
        self.system_root = system_root

        self.patch_dir = os.path.join(patches_dir, self.name)
        self.source_dir = os.path.join(sources_dir, self.dir)

        self.version = source_properties["version"]

        if "url" in source_properties:
            self.source_type = SourceType.URL
            self.url = source_properties["url"]
            self.format = source_properties["format"]
        else:
            self.source_type  = SourceType.GIT
            self.git = source_properties["git"]

            if "branch" in source_properties:
                self.branch = source_properties["branch"]
                self.clone_type = CloneType.BRANCH
            else:
                self.branch = "master"
                if "commit" in source_properties:
                    self.clone_type = CloneType.COMMIT
                    self.commit = source_properties["commit"]
                else:
                    self.clone_type = CloneType.TAG
                    self.tag = source_properties["tag"]

        if "extract-path" in source_properties:
            self.extract_path = source_properties["extract-path"]
        else:
            self.extract_path = self.name + '-' + self.version

        if "extract-strip" in source_properties:
            self.extract_strip = int(source_properties["extract-strip"])
        else:
            self.extract_strip = 0

        if "patch-path-strip" in source_properties:
            self.patch_path_strip = source_properties["patch-path-strip"]
        else:
            self.patch_path_strip = 0

        if "tools-required" in source_properties:
            self.tools_required = source_properties["tools-required"]
        else:
            self.tools_required = []

        self.regenerate_steps: list[Step] = []
        if "regenerate" in source_properties:
            regenerate_properties = source_properties["regenerate"]
            for step in regenerate_properties:
                self.regenerate_steps.append(Step(step, self))

    def acquire(self):
        with Progress() as progress:
            if self.source_type == SourceType.URL:
                download_progress = DownloadProgress(self.url, self.sources_dir, progress)
                download_progress.acquire()

            elif self.source_type == SourceType.GIT:
                # repo, branch, commit, tag
                clone_progress = CloneProgress(progress)

                repo = git.Repo.clone_from(self.git, self.source_dir, branch = self.branch, progress = clone_progress)
                if self.clone_type == CloneType.COMMIT:
                    repo.git.checkout(self.commit)
                elif self.clone_type == CloneType.TAG:
                    repo.git.checkout(self.tag)

    def extract(self):
        if self.source_type is not SourceType.URL:
            return

        def strip_root(member: TarInfo):
            return member.replace(name = pathlib.Path(*pathlib.Path(member.path).parts[self.extract_strip:]))

        def track_progress(members: list[TarInfo]):
            for member in members:
                member = strip_root(member)
                progress.update(extract_bar, advance = member.size)

                yield member

        with Progress() as progress:
            parsed_url = urlparse(self.url)
            output_file = os.path.basename(parsed_url.path)
            total_bytes = os.stat(os.path.join(self.sources_dir, output_file)).st_size

            extract_bar = progress.add_task("[red] Extracting...", totla = total_bytes)

            if self.format == 'tar.xz' or self.format == 'tar.gz':
                with tarfile.open(os.path.join(self.sources_dir, output_file)) as tar:
                    tar.extractall(path=self.source_dir, members = track_progress(tar))

            progress.stop_task(extract_bar)

    def apply_patches(self):
        for dir, _, files in os.walk(self.patch_dir):
            for file in files:
                patch_path = os.path.join(dir, file)
                print(patch_path)

            try:
                res = subprocess.check_output([f"patch -f -p1 < {patch_path}"], cwd=self.source_dir, shell=True,
                    stderr=subprocess.STDOUT, universal_newlines=True)
                print(res)
            except CalledProcessError as err:
                rich_print(f"[red] Error patching source package {self.name}: exit {err.returncode}")
                raise err

    def deps(self):
        deps = []
        for tool in self.tools_required:
            deps.append(tool)

        return deps

    def make_dirs(self):
        os.makedirs(self.source_dir, exist_ok = True)

    def clean_dirs(self, sources_dir):
        if os.path.exists(self.source_dir):
            shutil.rmtree(self.source_dir)

    def prepare(self):
        self.acquire()
        self.extract()
        self.apply_patches()

    def exec_steps(self, steps: list[Step]):
        for step in steps:
            step.exec(
                self.system_prefix,
                self.system_targets,
                self.sources_dir,
                self.sources_dir,

                self.source_dir,
                self.source_dir,

                self.source_dir,
                self.system_root
            )

    def regenerate(self):
        self.exec_steps(self.regenerate_steps)

    def __str__(self):
        return f"Source {self.name}[{self.version}]"

    def __repr__(self):
        return self.__str__()