import os

from enum import Enum
import shutil
import subprocess

from .step import Step
from .source import SourcePackage
from .stage import Stage

class ToolPackage:
    def __init__(self, source_data, sources_dir,  builds_dir, tools_dir, system_targets, system_prefix, system_root):
        source_properties = source_data

        self.name = source_properties["name"]
        self.version = source_properties["version"]

        self.sources_dir = sources_dir
        self.builds_dir = builds_dir
        self.tools_dir = tools_dir

        self.build_dir = os.path.join(builds_dir, self.name)
        self.tool_dir = os.path.join(tools_dir, self.name)
        self.system_prefix = system_prefix
        self.system_targets = system_targets
        self.system_root = system_root

        self.source = None
        self.source_dir = None
        self.source_name = source_properties["from_source"]

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

        self.compile_steps: list[Step]  = []
        if "compile" in source_properties:
            compile_properties = source_properties["compile"]
            for step in compile_properties:
                self.compile_steps.append(Step(step, self))

        self.install_steps: list[Step]  = []
        if "install" in source_properties:
            install_properties = source_properties["install"]
            for step in install_properties:
                self.install_steps.append(Step(step, self))

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
        self.source = source_package
        self.source_dir = source_package.source_dir
        for stage in self.stages:
            stage.link_source(source_package)

    def make_dirs(self):
        os.makedirs(self.tool_dir, exist_ok = True)
        os.makedirs(self.build_dir, exist_ok = True)

    def prune_prefix(self):
        deleted = set()
        for dir, subdirs, files in os.walk(self.system_prefix, topdown=False):
            still_has_subdirs = False
            for subdir in subdirs:
                if os.path.join(dir, subdir) not in deleted:
                    still_has_subdirs = True
                    break

            if not any(files) and not still_has_subdirs:
                os.rmdir(dir)
                deleted.add(dir)

    def clean_dirs(self):
        pkg_root_dir = self.tool_dir

        for dir, _, files in os.walk(pkg_root_dir):
            for f in files:
                f_path = os.path.join(dir, f)
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

    def exec_steps(self, steps: list[Step]):
        for step in steps:
            step.exec(
                self.system_prefix,
                self.system_targets,
                self.sources_dir,
                self.builds_dir,

                self.source_dir,
                self.build_dir,

                self.tool_dir,
                self.system_root
            )

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