import os

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
    
    @property
    def stage_deps(self):
        stage_deps = {}
        for stage in self.stages:
            stage_deps[f"{self.name}[{stage.name}]"] = stage.deps()
        
        return stage_deps

    def find_stage(self, name):
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

    def make_dirs(self, packages_dir):
        os.makedirs(os.path.join(packages_dir, self.dir), exist_ok = True)

    def configure(self, sources_dir,  packages_dir, system_prefix, system_target, system_dir, stage_name: str = None):
        if stage_name is None:
            for step in self.configure_steps:
                step.exec(system_prefix, system_target, sources_dir, packages_dir, system_dir)
        else:
            stage = self.find_stage(stage_name)
            
            for step in stage.configure_steps:
                step.exec(system_prefix, system_target, system_target, sources_dir, packages_dir, system_dir)

    def build(self, sources_dir,  packages_dir, system_prefix, system_target, system_dir, stage_name: str = None):
        if stage_name is None:
            for step in self.build_steps:
                step.exec(system_prefix, system_target, sources_dir, packages_dir, system_dir)
        else:
            stage = self.find_stage(stage_name)
            
            for step in stage.build_steps:
                step.exec(system_prefix, system_target, sources_dir, packages_dir, system_dir)

    def __str__(self):
        return f"Package {self.name}[{self.version}]"
    
    def __repr__(self):
        return self.__str__()