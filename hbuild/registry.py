from pathlib import Path

import toml
import yaml

from copy import deepcopy
from .config import HPackageConfig
from .source import SourcePackage
from .step import Step
from .tool import ToolPackage
from .package import Package
from .stage import Stage

import json
from jsonschema import Draft7Validator
import os

from referencing import Registry
from referencing.jsonschema import DRAFT7

class HPackageRegistry():
    def __init__(self):
        self.config = {}
        self.schemas = {}
        self.registry = Registry()

        self.load_config()
        self.load_schemas()

        self.logs_dir = Path(self.config["hbuild"]["logs_dir"]).resolve().as_posix()

        self.sources_dir = Path(self.config["hbuild"]["sources_dir"]).resolve().as_posix()
        self.tools_dir = Path(self.config["hbuild"]["tools_dir"]).resolve().as_posix()
        self.packages_dir = Path(self.config["hbuild"]["packages_dir"]).resolve().as_posix()
        self.builds_dir = Path(self.config["hbuild"]["builds_dir"]).resolve().as_posix()
        self.works_dir = Path(self.config["hbuild"]["works_dir"]).resolve().as_posix()

        self.patches_dir = Path(self.config["hbuild"]["patches_dir"]).resolve().as_posix()

        self.system_root = Path(self.config["hbuild"]["system"]["files"]).resolve().as_posix()
        self.system_prefix = Path(self.config["hbuild"]["system"]["prefix"]).resolve().as_posix()

        self.system_targets = self.config["hbuild"]["system"]["targets"]

        self.file_configs: list[HPackageConfig] = []

        self.stages: list[Stage] = []
        self.sources: list[SourcePackage] = []
        self.tools: list[ToolPackage] = []
        self.packages: list[Package] = []

        self.load_pkgsrc_dir()
        self.load_sources()
        self.load_tools()
        self.load_packages()

    @property
    def stage_names(self):
        names = []
        for package in self.packages:
            stage_names = [f"{package.name}[{k.name}]" for k in package.stages]
            names = [*names, *stage_names]
        for tool in self.tools:
            stage_names = [f"{tool.name}[{k.name}]" for k in tool.stages]
            names = [*names, *stage_names]

        return names

    @property
    def package_names(self):
        names = []
        for package in self.packages:
            names.append(package.name)

        return names

    @property
    def tool_names(self):
        names = []
        for tool in self.tools:
            names.append(tool.name)

        return names

    @property
    def source_names(self):
        names = []
        for source in self.sources:
            names.append(source.name)

        return names

    def is_package(self, package):
        if package in self.package_names:
            return True

        return False

    def is_tool(self, tool):
        if tool in self.tool_names:
            return True

        return False

    def is_source(self, source):
        if source in self.source_names:
            return True

        return False

    def find_source(self, name):
        for source in self.sources:
            if source.name == name:
                return source

        return None

    def find_tool(self, name):
        for tool in self.tools:
            if tool.name == name:
                return tool

        return None

    def find_package(self, name):
        for package in self.packages:
            if package.name == name:
                return package

        return None

    def load_config(self) -> None:
        with open("config.toml") as f:
            self.config = toml.load(f)

    def load_schema(self, schema_file: str) -> object:
        with open(schema_file) as f:
            schema_json = json.load(f)
            return schema_json["$id"], schema_json

    def load_schemas(self) -> None:
        for dir, _, files in os.walk(self.config["hbuild"]["schema_dir"]):
            for file in files:
                schema_path = Path(dir, file).resolve().as_posix()
                schema_id, schema_json = self.load_schema(schema_path)
                schema_name = schema_id.split('/')[4]

                schema = DRAFT7.create_resource(schema_json)

                self.registry = self.registry.with_resource(schema_id, schema)
                self.schemas[schema_name] = schema_json

    def load_pkgsrc(self, pkgsrc_file: str) -> dict[str, str]:
        with open(pkgsrc_file) as f:
            return yaml.load(f, Loader=yaml.CLoader)

    def load_pkgsrc_dir(self) -> None:
        for dent, _, files in os.walk(self.config["hbuild"]["pkgsrc_dir"]):
            for file in files:
                pkgsrc_path = Path(dent, file).resolve().as_posix()
                pkgsrc_yml: dict[str, str] = self.load_pkgsrc(pkgsrc_path)

                pkgsrc_validator = Draft7Validator(self.schemas["pkgsrc"], registry=self.registry)
                pkgsrc_validator.validate(pkgsrc_yml)

                build_config = HPackageConfig(
                    Path(self.logs_dir),
                    Path(self.sources_dir),
                    None,
                    Path(self.patches_dir),
                    self.system_targets,
                    Path(self.system_prefix),
                    Path(self.system_root),
                    Path(self.tools_dir),
                    Path(self.packages_dir),
                    Path(self.builds_dir),
                    Path(self.works_dir),
                    pkgsrc_yml
                )

                self.file_configs.append(build_config)

    def load_steps(self, package: Package | ToolPackage | SourcePackage | Stage):
        if isinstance(package, SourcePackage):
            for step_yml in package.regenerate_ymls:
                final_config = deepcopy(package.config)
                final_config.pkgsrc_yml = step_yml

                package.regenerate_steps.append(Step(final_config, package.name))
        if isinstance(package, ToolPackage):
            for step_yml in package.configure_ymls:
                final_config = deepcopy(package.config)
                final_config.pkgsrc_yml = step_yml

                package.configure_steps.append(Step(final_config, package.name))
            for step_yml in package.compile_ymls:
                final_config = deepcopy(package.config)
                final_config.pkgsrc_yml = step_yml

                package.compile_steps.append(Step(final_config, package.name))
            for step_yml in package.install_ymls:
                final_config = deepcopy(package.config)
                final_config.pkgsrc_yml = step_yml

                package.install_steps.append(Step(final_config, package.name))
        if isinstance(package, Package):
            for step_yml in package.configure_ymls:
                final_config = deepcopy(package.config)
                final_config.pkgsrc_yml = step_yml

                package.configure_steps.append(Step(final_config, package.name))
            for step_yml in package.build_ymls:
                final_config = deepcopy(package.config)
                final_config.pkgsrc_yml = step_yml

                package.build_steps.append(Step(final_config, package.name))
        if isinstance(package, Stage):
            for step_yml in package.compile_ymls:
                final_config = deepcopy(package.config)
                final_config.pkgsrc_yml = step_yml

                package.compile_steps.append(Step(final_config, package.name))
            for step_yml in package.build_ymls:
                final_config = deepcopy(package.config)
                final_config.pkgsrc_yml = step_yml

                package.build_steps.append(Step(final_config, package.name))
            for step_yml in package.install_ymls:
                final_config = deepcopy(package.config)
                final_config.pkgsrc_yml = step_yml

                package.install_steps.append(Step(final_config, package.name))

    def load_stages(self, package: ToolPackage | Package):
        if isinstance(package, ToolPackage):
            for stage_yml in package.stage_ymls:
                final_config = deepcopy(package.config)
                final_config.pkgsrc_yml = stage_yml

                stage = Stage(final_config, package, package.name)
                self.load_steps(stage)

                package.stages.append(stage)
                self.stages.append(stage)

    def load_sources(self):
        for build_config in self.file_configs:
            if "source" in build_config.pkgsrc_yml:
                final_config = deepcopy(build_config)
                final_config.pkgsrc_yml = build_config.pkgsrc_yml["source"]

                source_validator = Draft7Validator(self.schemas["source"], registry=self.registry)
                source_validator.validate(build_config.pkgsrc_yml["source"])

                source_package = SourcePackage(final_config)
                self.load_steps(source_package)
                self.sources.append(source_package)

    def load_tools(self):
        for build_config in self.file_configs:
            if "tools" in build_config.pkgsrc_yml:
                for tool_yml in build_config.pkgsrc_yml["tools"]:
                    final_config = deepcopy(build_config)
                    final_config.pkgsrc_yml = tool_yml

                    source_name = tool_yml["from_source"]
                    source = self.find_source(source_name)
                    if source is None:
                        raise ValueError(f"Could not find source {source_name} for tool package {tool_yml['name']}")
                    final_config.source_dir = source.source_dir

                    tool_validator = Draft7Validator(self.schemas["tool"], registry=self.registry)
                    tool_validator.validate(tool_yml)

                    tool_package = ToolPackage(final_config)
                    self.load_steps(tool_package)
                    self.load_stages(tool_package)
                    self.tools.append(tool_package)

    def load_packages(self):
        for build_config in self.file_configs:
            if "packages" in build_config.pkgsrc_yml:
                for package_yml in build_config.pkgsrc_yml["packages"]:
                    final_config = deepcopy(build_config)
                    final_config.pkgsrc_yml = package_yml

                    source_name = package_yml["from_source"]
                    source = self.find_source(source_name)
                    if source is None:
                        raise ValueError(f"Could not find source {source_name} for system package {package_yml['name']}")
                    final_config.source_dir = source.source_dir

                    package_validator = Draft7Validator(self.schemas["package"], registry=self.registry)
                    package_validator.validate(package_yml)

                    package = Package(final_config)
                    self.load_steps(package)
                    self.load_stages(package)
                    self.packages.append(package)