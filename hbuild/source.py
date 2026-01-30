import os
import shutil
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse

import podman
from persistqueue import FIFOSQLiteQueue
from podman.domain.containers import Container as PodmanContainer

from .step import Step
from .config import HPackageConfig

class SourceType(Enum):
    URL = 1
    GIT = 2

class CloneType(Enum):
    COMMIT = 0
    BRANCH = 1
    TAG = 2

class SourcePackage:
    def __init__(self, config: HPackageConfig):
        self.config = config

        source_properties = config.pkgsrc_yml

        self.name = source_properties["name"]

        if "subdir" in source_properties:
            self.subdir = source_properties["subdir"]
            self.dir = os.path.join(self.subdir, self.name)
        else:
            self.dir = self.name

        self.patches_dir = config.patches_dir
        self.logs_dir = config.logs_dir
        self.sources_dir = config.sources_dir

        self.system_prefix = config.system_prefix
        self.system_targets = config.system_targets
        self.system_root = config.system_root

        self.log_dir = Path(config.logs_dir, f"source[{self.name}]").resolve().as_posix()
        self.patch_dir = Path(config.patches_dir, self.name).resolve().as_posix()
        self.source_dir = Path(config.sources_dir, self.dir).resolve().as_posix()

        self.podman_client = podman.from_env()
        self.podman_container: PodmanContainer | None = None

        self.last_return_status = None

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
                self.branch = None
                if "commit" in source_properties:
                    self.clone_type = CloneType.COMMIT
                    self.commit = source_properties["commit"]
                else:
                    self.clone_type = CloneType.TAG
                    self.tag = source_properties["tag"]

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

        self.acquire_steps: list[Step] = []
        self.extract_steps: list[Step] = []

        if self.source_type == SourceType.GIT:
            if self.branch is None:
                self.acquire_steps.append(Step({
                    "args": ["git", "clone", self.git, '/home/hbuild/source']
                }, self.name))
            else:
                self.acquire_steps.append(Step({
                    "args": ["git", "clone", "-b", self.branch, self.git, '/home/hbuild/source']
                }, self.name))

            if self.clone_type == CloneType.COMMIT or self.clone_type == CloneType.TAG:
                self.acquire_steps.append(Step({
                    "args": ["git", "checkout", self.commit if self.clone_type == CloneType.COMMIT else self.tag],
                }, self.name))
        else:
            self.acquire_steps.append(Step({
                "args": ["wget", self.url, "-P", '/home/hbuild/source_root']
            }, self.name))
        
        if self.source_type == SourceType.URL:
            parsed_url = urlparse(self.url)
            output_file = os.path.basename(parsed_url.path)
            
            self.extract_steps.append(Step({
                "args": ["tar", "-xvf" if self.format == "tar.xz" else "-xzvf", f"/home/hbuild/source_root/{output_file}",  "-C", '/home/hbuild/source', "--strip-components=1"]
            }, self.name))

        self.patch_steps: list[Step] = [Step({
            "args": "find @THIS_SOURCE_DIR@ -type f -name '*.patch' -print0 | xargs -0 -n 1 patch -p1",
            "shell": True
        }, self.name)]

        self.regenerate_ymls: list[dict[str, str]] = []
        self.regenerate_steps: list[Step] = []

        if "regenerate" in source_properties:
            regenerate_properties = source_properties["regenerate"]
            for step_yml in regenerate_properties:
                self.regenerate_ymls.append(step_yml)

    def acquire(self):
        self.exec_steps(self.acquire_steps)
        
    def extract(self):
        self.exec_steps(self.extract_steps)

    def apply_patches(self):
        pass
        #self.exec_steps(self.patch_steps)

    def deps(self):
        deps = []
        for tool in self.tools_required:
            deps.append(tool)

        return deps

    def make_container(self):
        if self.podman_container is not None:
            pass
        self.podman_container = self.podman_client.containers.run(
            'hbuild:latest',
            stdout=True,
            stderr=True,
            userns_mode='keep-id',

            volumes = {
                self.source_dir: {
                    'bind': '/home/hbuild/source',
                    'mode': 'rw',
                    'extended_mode': ['U', 'z']
                },

                self.system_prefix: {
                    'bind': '/home/hbuild/system_prefix',
                    'mode': 'ro',
                    'extended_mode':  ['z']
                },

                self.system_root: {
                    'bind': '/home/hbuild/system_root',
                    'mode': 'ro',
                    'extended_mode': ['z']
                },

                self.sources_dir: {
                    'bind': '/home/hbuild/source_root',
                    'mode': 'rw',
                    'extended_mode': ['U', 'z']
                },
                self.patches_dir: {
                    'bind': '/home/hbuild/patch_root',
                    'mode': 'ro',
                    'extended_mode': [ 'z']
                },
            } |
            (
                 {
                    self.patch_dir: {
                        'bind': '/home/hbuild/patch',
                        'mode': 'ro',
                        'extended_mode': ['z']
                    }
                } if Path(self.patch_dir).exists() is True else {}
            ),

            detach=True,
            tty=True
        )

    def kill_build(self):
        self.podman_container.kill(signal='SIGKILL')

    def tidy(self):
        if self.podman_container is not None:
            self.podman_container.kill(signal='SIGKILL')
            self.podman_container.remove(force=True)
            self.podman_container = None

    def make_dirs(self):
        os.makedirs(self.source_dir, exist_ok = True)

    def clean_dirs(self):
        if os.path.exists(self.source_dir):
            shutil.rmtree(self.source_dir)

    def prepare(self):
        self.acquire()
        self.extract()
        self.apply_patches()

    def exec_steps(self, steps: list[Step]) -> int | Exception:
        return_code: int | Exception = None
        for step in steps:
            return_code = step.exec(
                '/home/hbuild/system_prefix',
                self.system_targets,
                '/home/hbuild/source_root',
                '/home/hbuild/source_root',

                '/home/hbuild/source',
                '/home/hbuild/source',

                '/home/hbuild/source',
                '/home/hbuild/system_root',

                self.podman_container,
                self
            )

            if isinstance(return_code, Exception):
                break

        return return_code


    def regenerate(self):
        self.exec_steps(self.regenerate_steps)

    def __str__(self):
        return f"Source {self.name}[{self.version}]"

    def __repr__(self):
        return self.__str__()