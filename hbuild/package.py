import math
import os
import shutil
import subprocess

from enum import Enum

from .step import Step
from .source import SourcePackage
from .stage import Stage

class PackageSourceType(Enum):
    EXTERNAL_SOURCE = 1
    IMPLICIT_SOURCE = 2

class Package:
    def __init__(self, source_data, source_package: SourcePackage):
        source_properties = source_data

        self.name = source_properties["name"]
        self.version = source_properties["version"]

        self.dir = self.name

        if "from_source" in source_properties:
            self.source_type = PackageSourceType.EXTERNAL_SOURCE
            self.source = source_properties["from_source"]

            self.source_dir = source_package.source_dir
        else:
            self.source_type = PackageSourceType.IMPLICIT_SOURCE
            self.source = SourcePackage(source_properties["source"], implicit_source = True, tool_package = self)

            self.source_dir = self.source.source_dir

        self.metadata = source_properties["metadata"]

        if "system-package" in source_properties:
            self.system_package = True
        else:
            self.system_package = False

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

        self.has_configured = False
        self.has_built = False

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

        if self.source_type == PackageSourceType.IMPLICIT_SOURCE:
            deps.append(f"source[{self.source.name}]")
            for tool in self.source.tools_required:
                deps.append(tool)
        else:
            deps.append(f"source[{self.source}]")

        return deps

    def make_dirs(self, packages_dir, builds_dir):
        os.makedirs(os.path.join(packages_dir, self.dir), exist_ok = True)
        os.makedirs(os.path.join(builds_dir, self.dir), exist_ok = True)

    def prune_system(self, system_dir):
        deleted = set()
        for dir, subdirs, files in os.walk(system_dir, topdown=False):
            still_has_subdirs = False
            for subdir in subdirs:
                if os.path.join(dir, subdir) not in deleted:
                    still_has_subdirs = True
                    break

            if not any(files) and not still_has_subdirs:
                os.rmdir(dir)
                deleted.add(dir)

    def clean_dirs(self, packages_dir, builds_dir, system_dir):
        pkg_root_dir = os.path.join(packages_dir, self.dir)
        pkg_files = []

        for dir, _, files in os.walk(os.path.join(packages_dir, self.dir)):
            for f in files:
                f_path = os.path.join(dir, f)
                if os.path.lexists(f_path):
                    f_rel_path = os.path.relpath(f_path, pkg_root_dir)

                    f_pkg_path = os.path.join(pkg_root_dir, f_rel_path)
                    f_system_path =os.path.join(system_dir, f_rel_path)

                    if os.path.lexists(f_pkg_path):
                        os.unlink(f_pkg_path)

                    if os.path.lexists(f_system_path):
                        os.unlink(f_system_path)
                        
        if os.path.exists(os.path.join(builds_dir, self.dir)):
            shutil.rmtree(os.path.join(builds_dir, self.dir))
        if os.path.exists(os.path.join(packages_dir, self.dir)):
            shutil.rmtree(os.path.join(packages_dir, self.dir))
        self.prune_system(system_dir)

    def configure(self, sources_dir,  builds_dir, packages_dir, system_prefix, system_target, system_dir):
        for step in self.configure_steps:
            step.exec(system_prefix, system_target, sources_dir, builds_dir, packages_dir, system_dir)
        self.has_configured = True

    def build(self, sources_dir,  builds_dir, packages_dir, system_prefix, system_target, system_dir, stage: Stage = None):
        if stage is None:
            for step in self.build_steps:
                step.exec(system_prefix, system_target, sources_dir, builds_dir, packages_dir, system_dir)
            self.has_built = True
        else:
            for step in stage.build_steps:
                step.exec(system_prefix, system_target, sources_dir, builds_dir, packages_dir, system_dir)
            stage.has_built = True

    def files_size(self, packages_dir):
            total_size = 0
            for dir, subdirs, files in os.walk(os.path.join(packages_dir, self.dir)):
                for _ in subdirs:
                    total_size += 1024
                for file in files:
                    total_size += math.ceil(os.path.getsize(os.path.join(dir, file)) / 1024)

    def copy_system(self, packages_dir, system_dir):
        subprocess.run(['rsync', '-aq', '--exclude=DEBIAN',  f"{os.path.join(packages_dir, self.dir)}/", f"{system_dir}"])

    def format_description(self):
        return f"""Description: {self.metadata["summary"]}
 {self.metadata["description"]}"""

    def make_control(self, packages_dir, deps_dict: dict[str, str]):
        if len(deps_dict) > 0:
            deps: list[str] = [f"{name} (>={version})" for name, version in deps_dict.items()]

            return f"""Package: {self.name}
Version: {self.version}
Architecture: amd64
{self.format_description()}
Section: {self.metadata["section"]}
Maintainer: {self.metadata["maintainer"]}
Homepage: {self.metadata["website"]}
Installed-Size: {self.files_size(packages_dir)}
Depends: {", ".join(deps)}
"""
        else:
            return f"""Package: {self.name}
Version: {self.version}
Architecture: amd64
{self.format_description()}
Section: {self.metadata["section"]}
Maintainer: {self.metadata["maintainer"]}
Homepage: {self.metadata["website"]}
Installed-Size: {self.files_size(packages_dir)}
"""

    def make_deb(self, packages_dir, deps_dict: dict[str, str]):
        control_string = self.make_control(packages_dir, deps_dict)

        os.makedirs(os.path.join(packages_dir, self.dir, "DEBIAN"), exist_ok=True)
        with open(os.path.join(packages_dir, self.dir, "DEBIAN", "control"), 'w+') as control_file:
            control_file.write(control_string)

        subprocess.run(["dpkg-deb", "--root-owner-group", "--build", os.path.join(packages_dir, self.dir), packages_dir])

    def __str__(self):
        return f"Package {self.name}[{self.version}]"

    def __repr__(self):
        return self.__str__()