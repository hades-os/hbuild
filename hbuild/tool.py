from pathlib import Path

import podman
from podman.domain.containers import Container as PodmanContainer

import os

from enum import Enum
import shutil
import subprocess

from .config import HPackageConfig
from .step import Step
from .source import SourcePackage
from .stage import Stage

from persistqueue import FIFOSQLiteQueue

class ToolPackage:
    def __init__(self, config: HPackageConfig):
        self.config = config

        source_properties = config.pkgsrc_yml

        self.name = source_properties["name"]
        self.version = source_properties["version"]

        self.logs_dir = config.logs_dir
        self.sources_dir = config.sources_dir
        self.builds_dir = config.builds_dir
        self.tools_dir = config.tools_dir
        self.works_dir = config.works_dir

        self.log_dir = Path(self.logs_dir, self.name).resolve().as_posix()
        self.work_dir = Path(self.works_dir, self.name).resolve().as_posix()
        self.build_dir = Path(config.builds_dir, self.name).resolve().as_posix()
        self.tool_dir = Path(config.tools_dir, self.name).resolve().as_posix()
        self.system_prefix = config.system_prefix
        self.system_targets = config.system_targets
        self.system_root = config.system_root

        self.source_dir = config.source_dir
        self.source_name = source_properties["from_source"]

        self.podman_client = podman.from_env()
        self.podman_container: PodmanContainer = None

        self.last_return_status = None

        if "tools-required" in source_properties:
            self.tools_required = source_properties["tools-required"]
        else:
            self.tools_required = []
        
        if "pkgs-required" in source_properties:
            self.pkgs_required = source_properties["pkgs-required"]
        else:
            self.pkgs_required = []

        self.configure_ymls: list[dict[str, str]] = []
        self.compile_ymls: list[dict[str, str]] = []
        self.install_ymls: list[dict[str, str]] = []
        self.stage_ymls: list[dict[str, str]] = []

        self.configure_steps: list[Step] = []
        self.compile_steps: list[Step]  = []
        self.install_steps: list[Step]  = []
        self.stages: list[Stage] = []

        if "configure" in source_properties:
            configure_properties = source_properties["configure"]
            for step_yml in configure_properties:
                self.configure_ymls.append(step_yml)

        if "compile" in source_properties:
            configure_properties = source_properties["compile"]
            for step_yml in configure_properties:
                self.compile_ymls.append(step_yml)

        if "install" in source_properties:
            configure_properties = source_properties["install"]
            for step_yml in configure_properties:
                self.install_ymls.append(step_yml)

        if "stages" in source_properties:
            stages_properties = source_properties["stages"]
            for stage_yml in stages_properties:
                self.stage_ymls.append(stage_yml)

    @property
    def num_stages(self):
        return len(self.stages)

    @property
    def stage_deps(self):
        stage_deps = {}
        for stage in self.stages:
            stage_deps[f"{self.name}[{stage.name}]"] = [*self.deps(), *stage.deps()]

        return stage_deps
    
    def find_stage(self, name) -> Stage:
        for stage in self.stages:
            if stage.name == name:
                return stage
        
        return None
    
    def deps(self):
        deps = []
        for tool in self.tools_required:
            if isinstance(tool, dict):
                if "stage-dependencies" in tool:
                    for stage_dep in tool["stage-dependencies"]:
                        deps.append(f"{tool['tool']}[{stage_dep}]")
                else:
                    deps.append(tool["tool"])
            else:
                deps.append(tool)

        for pkg in self.pkgs_required:
            deps.append(pkg)

        deps.append(f"source[{self.source_name}]")
        return deps

    def link_source(self, source_package: SourcePackage):
        self.source_dir = source_package.source_dir
        for stage in self.stages:
            stage.link_source(source_package)

    def make_container(self):
        if self.podman_container is not None:
            pass        
        self.podman_container = self.podman_client.containers.run(
            'hbuild:latest',
            stdout=True,
            stderr=True,
            userns_mode='keep-id',

            overlay_volumes=[
                {
                    'source': self.system_prefix,
                    'destination': '/home/hbuild/system_prefix',
                    'options': [
                        'U',
                        'z',
                        f'upperdir={self.tool_dir}',
                        f'workdir={self.work_dir}'
                    ]
                }
            ],

            volumes={
                self.source_dir: { 
                    'bind': '/home/hbuild/source', 
                    'mode': 'rw', 
                    'extended_mode': ['U', 'z']
                },

                self.build_dir: { 
                    'bind': '/home/hbuild/build', 
                    'mode': 'rw', 
                    'extended_mode': ['U', 'z']
                },

                self.tool_dir: { 
                    'bind': '/home/hbuild/tool', 
                    'mode': 'rw',
                    'extended_mode': ['U', 'z']
                },

                self.system_root: { 
                    'bind': '/home/hbuild/system_root', 
                    'mode': 'ro',
                    'extended_mode': ['z']
                },

                self.sources_dir: { 
                    'bind': '/home/hbuild/source_root', 
                    'mode': 'ro',
                    'extended_mode': ['z']
                },
                self.builds_dir: { 
                    'bind': '/home/hbuild/build_root', 
                    'mode': 'ro',
                    'extended_mode': [ 'z']
                },
            },

            detach=True,
            tty=True
        )

    def tidy(self):
        if self.podman_container is not None:
            self.podman_container.kill(signal='SIGKILL')
            self.podman_container.remove(force=True)
            self.podman_container = None

    def make_dirs(self):
        os.makedirs(self.work_dir, exist_ok=True)
        os.makedirs(self.tool_dir, exist_ok = True)
        os.makedirs(self.build_dir, exist_ok = True)

    def prune_prefix(self):
        deleted = set()
        for dent, subdir, files in os.walk(self.system_prefix, topdown=False):
            still_has_subdirs = False
            for subent in subdir:
                if os.path.join(dent, subent) not in deleted:
                    still_has_subdirs = True
                    break

            if not any(files) and not still_has_subdirs:
                os.rmdir(dent)
                deleted.add(dent)

    def clean_dirs(self):
        pkg_root_dir = self.tool_dir

        for dent, _, files in os.walk(pkg_root_dir):
            for f in files:
                f_path = os.path.join(dent, f)
                if os.path.lexists(f_path):
                    f_rel_path = os.path.relpath(f_path, pkg_root_dir)

                    f_pkg_path = os.path.join(pkg_root_dir, f_rel_path)
                    f_system_path =os.path.join(self.system_prefix, f_rel_path)

                    if os.path.lexists(f_pkg_path):
                        os.unlink(f_pkg_path)

                    if os.path.lexists(f_system_path):
                        os.unlink(f_system_path)
                        
        if os.path.exists(self.build_dir):
            shutil.rmtree(self.build_dir)
        if os.path.exists(self.tool_dir):
            shutil.rmtree(self.tool_dir)
        self.prune_prefix()

    def exec_steps(self, steps: list[Step]) -> int | Exception:
        return_code: int | Exception = None
        for step in steps:
            step.exec(
                '/home/hbuild/system_prefix',
                self.system_targets,
                '/home/hbuild/source_root',
                '/home/hbuild/build_root',

                '/home/hbuild/source',
                '/home/hbuild/build',

                '/home/hbuild/tool',
                '/home/hbuild/system_root',

                self.podman_container,
                self
            )

            if isinstance(return_code, Exception):
                break
        
        return return_code

    def kill_build(self):
        self.podman_container.kill(signal='SIGKILL')

    def configure(self):
        self.exec_steps(self.configure_steps)

    def compile(self, stage: Stage = None):
        if stage is None:
            self.exec_steps(self.compile_steps)
        else:
            self.exec_steps(stage.compile_steps)

    def install(self, stage: Stage = None):
        if stage is None:
            self.exec_steps(self.install_steps)
        else:            
            self.exec_steps(stage.install_steps)

    def copy_tool(self):
        subprocess.run(['rsync', '-aq',  f"{self.tool_dir}/", f"{self.system_prefix}"])

    def __str__(self):
        return f"Tool {self.name}[{self.version}]"
    
    def __repr__(self):
        return self.__str__()