import math
import os
import shutil
import subprocess
from pathlib import Path

import podman
from persistqueue import FIFOSQLiteQueue
from podman.domain.containers import Container as PodmanContainer

from .config import HPackageConfig
from .source import SourcePackage
from .stage import Stage
from .step import Step

class Package:
    def __init__(self, config: HPackageConfig):
        self.config = config

        source_properties = config.pkgsrc_yml

        self.name = source_properties["name"]
        self.version = source_properties["version"]

        self.logs_dir = config.logs_dir
        self.sources_dir = config.sources_dir
        self.builds_dir = config.builds_dir
        self.packages_dir = config.packages_dir
        self.works_dir = config.works_dir

        self.log_dir = Path(config.logs_dir, self.name).resolve().as_posix()
        self.work_dir = Path(self.works_dir, self.name).resolve().as_posix()
        self.build_dir = Path(config.builds_dir, self.name).resolve().as_posix()
        self.package_dir = Path(config.packages_dir, self.name).resolve().as_posix()
        self.system_prefix = config.system_prefix
        self.system_targets = config.system_targets
        self.system_root = config.system_root

        self.source_dir = config.source_dir
        self.source_name = source_properties["from_source"]

        self.podman_client = podman.from_env()
        self.podman_container: PodmanContainer = None

        self.last_return_status = None

        self.metadata = source_properties["metadata"]

        if "system-package" in source_properties:
            self.system_package = True
        else:
            self.system_package = False

        if "no-deps" in source_properties:
            self.no_deps = True
        else:
            self.no_deps = False

        if "tools-required" in source_properties:
            self.tools_required = source_properties["tools-required"]
        else:
            self.tools_required = []

        if "pkgs-required" in source_properties:
            self.pkgs_required = source_properties["pkgs-required"]
        else:
            self.pkgs_required = []

        self.configure_ymls: list[dict[str, str]] = []
        self.build_ymls: list[dict[str, str]] = []
        self.stage_ymls: list[dict[str, str]] = []

        self.configure_steps: list[Step] = []
        self.build_steps: list[Step] = []
        self.stages: list[Stage] = []

        if "configure" in source_properties:
            configure_properties = source_properties["configure"]
            for step_yml in configure_properties:
                self.configure_ymls.append(step_yml)

        if "build" in source_properties:
            build_properties = source_properties["build"]
            for step_yml in build_properties:
                self.build_ymls.append(step_yml)

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

    def find_stage(self, name):
        for stage in self.stages:
            if stage.name == name:
                return stage

        return None

    def pkg_deps(self):
        deps = []
        for pkg in self.pkgs_required:
            deps.append(pkg)

        return deps

    def deps(self):
        deps = []
        for tool in self.tools_required:
            if isinstance(tool, dict):
                if "stage-dependencies" in tool:
                    for stage_dep in tool["stage-dependencies"]:
                        deps.append(f"{tool["tool"]}[{stage_dep}]")
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
                    'source': self.system_root,
                    'destination': '/home/hbuild/system_root', 
                    'options': [
                        f'upperdir={self.package_dir}',
                        f'workdir={self.work_dir}'
                    ],
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

                self.package_dir: { 
                    'bind': '/home/hbuild/package', 
                    'mode': 'rw',
                    'extended_mode': ['U', 'z']
                },

                self.system_prefix: { 
                    'bind': '/home/hbuild/system_prefix', 
                    'mode' : 'ro',
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

    def kill_build(self):
        self.podman_container.kill(signal='SIGKILL')

    def tidy(self):
        if self.podman_container is not None:
            self.podman_container.kill(signal='SIGKILL')
            self.podman_container.remove(force=True)
            self.podman_container = None

    def make_dirs(self):
        os.makedirs(self.work_dir, exist_ok=True)
        os.makedirs(self.package_dir, exist_ok = True)
        os.makedirs(self.build_dir, exist_ok = True)

    def prune_system(self):
        deleted = set()
        for dent, subdir, files in os.walk(self.system_root, topdown=False):
            still_has_subdir = False
            for subent in subdir:
                if os.path.join(dent, subent) not in deleted:
                    still_has_subdir = True
                    break

            if not any(files) and not still_has_subdir:
                os.rmdir(dent)
                deleted.add(dent)

    def clean_dirs(self):
        pkg_root_dir = self.package_dir

        for dent, _, files in os.walk(pkg_root_dir):
            for f in files:
                f_path = os.path.join(dent, f)
                if os.path.lexists(f_path):
                    f_rel_path = os.path.relpath(f_path, pkg_root_dir)

                    f_pkg_path = os.path.join(pkg_root_dir, f_rel_path)
                    f_system_path =os.path.join(self.system_root, f_rel_path)

                    if os.path.lexists(f_pkg_path):
                        os.unlink(f_pkg_path)

                    if os.path.lexists(f_system_path):
                        os.unlink(f_system_path)
                        
        if os.path.exists(self.build_dir):
            shutil.rmtree(self.build_dir)
        if os.path.exists(self.package_dir):
            shutil.rmtree(self.package_dir)
        self.prune_system()
    
    def exec_steps(self, steps: list[Step], stage: Stage | None) -> int | Exception:
        return_code: int | Exception = None
        for step in steps:
            return_code = step.exec(
                '/home/hbuild/system_prefix',
                self.system_targets,
                '/home/hbuild/source_root',
                '/home/hbuild/build_root',

                '/home/hbuild/source',
                '/home/hbuild/build',

                '/home/hbuild/package',
                '/home/hbuild/system_root',

                self.podman_container,
                self,
                stage
            )

            if isinstance(return_code, Exception):
                break
        
        return return_code

    def configure(self) -> int:
        return self.exec_steps(self.configure_steps, None)

    def build(self, stage: Stage = None) -> int:
        if stage is None:
            return self.exec_steps(self.build_steps, None)
        else:
            return self.exec_steps(stage.build_steps, stage)

    def files_size(self):
        total_size = 0
        for dent, subdir, files in os.walk(self.package_dir):
            for _ in subdir:
                total_size += 1024
            for file in files:
                total_size += math.ceil(os.path.getsize(os.path.join(dent, file)) / 1024)
        
        return total_size

    def copy_system(self):
        subprocess.run(['rsync', '-aq', '--exclude=DEBIAN',  f"{self.package_dir}/", f"{self.system_root}"])

    def format_description(self):
        return f"""Description: {self.metadata["summary"]}
 {self.metadata["description"]}"""

    def make_control(self, deps_dict: dict[str, str]):
        if len(deps_dict) > 0:
            deps: list[str] = [f"{name} (>={version})" for name, version in deps_dict.items()]

            return f"""Package: {self.name}
Version: {self.version}
Architecture: {self.metadata["architecture"] if "metadata" in self.metadata else "amd64"}
{self.format_description()}
Section: {self.metadata["section"]}
Maintainer: {self.metadata["maintainer"]}
Homepage: {self.metadata["website"]}
Installed-Size: {self.files_size()}
Depends: {", ".join(deps)}
"""
        else:
            return f"""Package: {self.name}
Version: {self.version}
Architecture: {self.metadata["architecture"] if "metadata" in self.metadata else "amd64"}
{self.format_description()}
Section: {self.metadata["section"]}
Maintainer: {self.metadata["maintainer"]}
Homepage: {self.metadata["website"]}
Installed-Size: {self.files_size()}
"""

    def make_deb(self, deps_dict: dict[str, str]):
        control_string = self.make_control(deps_dict)

        os.makedirs(os.path.join(self.package_dir, "DEBIAN"), exist_ok=True)
        with open(os.path.join(self.package_dir, "DEBIAN", "control"), 'w+') as control_file:
            control_file.write(control_string)

        subprocess.run(["dpkg-deb", "--root-owner-group", "--build",self.package_dir, self.packages_dir])

    def __str__(self):
        return f"Package {self.name}[{self.version}]"

    def __repr__(self):
        return self.__str__()