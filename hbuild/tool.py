import os

from enum import Enum
import shutil

from .step import Step
from .source import SourcePackage
from .stage import Stage

class ToolPackage:
    def __init__(self, source_data):
        source_properties = source_data

        self.name = source_properties["name"]
        self.version = source_properties["version"]

        self.dir = self.name

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

    def make_dirs(self, tools_dir, builds_dir):
        os.makedirs(os.path.join(tools_dir, self.dir), exist_ok = True)
        os.makedirs(os.path.join(builds_dir, self.dir), exist_ok = True)

    def clean_dirs(self, tools_dir, builds_dir):
        if os.path.exists(os.path.join(tools_dir, self.dir)):
            shutil.rmtree(os.path.join(tools_dir, self.dir))
        if os.path.exists(os.path.join(builds_dir, self.dir)):
            shutil.rmtree(os.path.join(builds_dir, self.dir))

    def configure(self, sources_dir,  builds_dir, tools_dir, system_prefix, system_targets, system_dir):
        for step in self.configure_steps:
            step.exec(system_prefix, system_targets, sources_dir, builds_dir, tools_dir, system_dir)

    def compile(self, sources_dir,  builds_dir, tools_dir, system_prefix, system_targets, system_dir, stage: Stage = None):
        if stage is None:
            for step in self.compile_steps:
                step.exec(system_prefix, system_targets, sources_dir, builds_dir, tools_dir, system_dir)
        else:
            for step in stage.compile_steps:
                step.exec(system_prefix, system_targets, sources_dir, builds_dir, tools_dir,system_dir)

    def install(self, sources_dir,  builds_dir, tools_dir, system_prefix, system_targets, system_dir, stage: Stage = None):
        if stage is None:
            for step in self.install_steps:
                step.exec(system_prefix, system_targets, sources_dir, builds_dir, tools_dir, system_dir)
        else:            
            for step in stage.install_steps:
                step.exec(system_prefix, system_targets, sources_dir, builds_dir, tools_dir, system_dir)

    def __str__(self):
        return f"Tool {self.name}[{self.version}]"
    
    def __repr__(self):
        return self.__str__()