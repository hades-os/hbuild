import docker

import math
import os
import shutil
import subprocess

from enum import Enum

from .step import Step
from .source import SourcePackage
from .stage import Stage

class Package:
    def __init__(self, source_data, sources_dir,  builds_dir, packages_dir, system_targets, system_prefix, system_root):
        source_properties = source_data

        self.name = source_properties["name"]
        self.version = source_properties["version"]

        self.sources_dir = sources_dir
        self.builds_dir = builds_dir
        self.packages_dir = packages_dir

        self.build_dir = os.path.join(builds_dir, self.name)
        self.package_dir = os.path.join(packages_dir, self.name)
        self.system_prefix = system_prefix
        self.system_targets = system_targets
        self.system_root = system_root

        self.source = None
        self.source_dir = None
        self.source_name = source_properties["from_source"]

        self.docker_client = docker.from_env()
        self.docker_container = self.docker_client.containers.run(
            'hbuild:latest',
            stdout=True,
            stderr=True,
            volumes={
                self.source_dir: { 'bind': '/home/hbuild/source', 'mode': 'rw' },
                self.build_dir: { 'bind': '/home/hbuild/build', 'mode': 'rw' },
                self.package_dir: { 'bind': '/home/hbuild/package', 'mode': 'rw' },

                self.system_prefix: { 'bind': '/home/hbuild/prefix', 'mode' : 'rw' },
                self.system_root: { 'bind': '/home/hbuild/root' },

                self.sources_dir: { 'bind': '/home/hbuild/source_root', 'mode': 'rw' },
                self.builds_dir: { 'bind': '/home/hbuild/build_root', 'mode': 'rw' },
            }   
        )

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

        self.configure_steps: list[Step] = []
        if "configure" in source_properties:
            configure_properties = source_properties["configure"]
            for step in configure_properties:
                self.configure_steps.append(Step(step, self))

        self.build_steps: list[Step] = []
        if "build" in source_properties:
            build_properties = source_properties["build"]
            for step in build_properties:
                self.build_steps.append(Step(step, self))

        self.stages: list[Stage] = []
        if "stages" in source_properties:
            stages_properties = source_properties["stages"]
            for stage in stages_properties:
                self.stages.append(Stage(stage, self))

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
        self.source = source_package
        self.source_dir = source_package.source_dir
        for stage in self.stages:
            stage.link_source(source_package)

    def make_dirs(self):
        os.makedirs(self.package_dir, exist_ok = True)
        os.makedirs(self.build_dir, exist_ok = True)

    def prune_system(self):
        deleted = set()
        for dir, subdirs, files in os.walk(self.system_root, topdown=False):
            still_has_subdirs = False
            for subdir in subdirs:
                if os.path.join(dir, subdir) not in deleted:
                    still_has_subdirs = True
                    break

            if not any(files) and not still_has_subdirs:
                os.rmdir(dir)
                deleted.add(dir)

    def clean_dirs(self):
        pkg_root_dir = self.package_dir

        for dir, _, files in os.walk(pkg_root_dir):
            for f in files:
                f_path = os.path.join(dir, f)
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
    
    def exec_steps(self, steps: list[Step]):
        for step in steps:
            step.exec(
                self.system_prefix,
                self.system_targets,
                self.sources_dir,
                self.builds_dir,

                self.source_dir,
                self.build_dir,

                self.package_dir,
                self.system_root
            )

    def configure(self):
        self.exec_steps(self.configure_steps)

    def build(self, stage: Stage = None):
        if stage is None:
            self.exec_steps(self.build_steps)
        else:
            self.exec_steps(stage.build_steps)

    def files_size(self):
            total_size = 0
            for dir, subdirs, files in os.walk(self.package_dir):
                for _ in subdirs:
                    total_size += 1024
                for file in files:
                    total_size += math.ceil(os.path.getsize(os.path.join(dir, file)) / 1024)

    def copy_system(self):
        subprocess.run(['rsync', '-aq', '--exclude=DEBIAN',  f"{self.package_dir}/", f"{self.system_dir}"])

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