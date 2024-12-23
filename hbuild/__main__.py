import json
import os
import re
import toml
import yaml

from pathlib import Path

from referencing import Registry
from referencing.jsonschema import DRAFT7

import rustworkx as rx
from rustworkx.visualization import graphviz_draw

from rich.markup import escape
from rich.tree import Tree
from rich import print as rich_print

from jsonschema import Draft7Validator

from .source import SourcePackage
from .tool import ToolPackage,ToolSourceType
from .package import Package, PackageSourceType

class HBuild:
    def __init__(self):
        self.load_config()

        self.registry = Registry()

        self.load_schemas()
        self.load_sources_yml()
        self.load_tools_yml()
        self.load_packages_yml()

        self.sources_dir = Path(self.config["hbuild"]["sources_dir"]).resolve().as_posix()
        self.tools_dir = Path(self.config["hbuild"]["tools_dir"]).resolve().as_posix()
        self.packages_dir = Path(self.config["hbuild"]["packages_dir"]).resolve().as_posix()
        self.builds_dir = Path(self.config["hbuild"]["builds_dir"]).resolve().as_posix()

        self.patches_dir = Path(self.config["hbuild"]["patches_dir"]).resolve().as_posix()

        self.system_dir = Path(self.config["hbuild"]["system"]["files"]).resolve().as_posix()
        self.system_prefix = Path(self.config["hbuild"]["system"]["prefix"]).resolve().as_posix()

        self.system_target = self.config["hbuild"]["system"]["target"]

        self.dep_graph = rx.PyDiGraph(check_cycle = True)

    def load_config(self) -> None:
        with open("config.toml") as f:
            self.config = toml.load(f)

    def load_schema(self, schema_file: str) -> object:
        with open(schema_file) as f:
            schema_json = json.load(f)
            return (schema_json["$id"], schema_json)

    def load_schemas(self) -> None:
        self.schemas = {}
        for subdir, dirs, files in os.walk(self.config["hbuild"]["schema_dir"]):
            for file in files:
                schema_path = os.path.join(subdir, file)
                schema_id, schema_json = self.load_schema(schema_path)
                schema_name = schema_id.split('/')[4]

                schema = DRAFT7.create_resource(schema_json)

                self.registry = self.registry.with_resource(schema_id, schema)
                self.schemas[schema_name] = schema_json

    def load_sources_yml(self) -> None:
        with open(self.config["hbuild"]["sources_yml"]) as f:
            self.sources_yml = yaml.load(f, Loader=yaml.CLoader)["sources"]

    def load_sources(self) -> None:
        self.sources: list[SourcePackage] = []
        for source_yml in self.sources_yml:
            source_validator = Draft7Validator(self.schemas["source"], registry = self.registry)
            source_validator.validate(source_yml)

            self.sources.append(SourcePackage(source_yml))

    def load_tools_yml(self) -> None:
        with open(self.config["hbuild"]["tools_yml"]) as f:
            self.tools_yml = yaml.load(f, Loader=yaml.CLoader)["tools"]

    def load_tools(self) -> None:
        self.tools: list[ToolPackage] = []
        for tool_yml in self.tools_yml:
            tool_validator = Draft7Validator(self.schemas["tool"], registry = self.registry)
            tool_validator.validate(tool_yml)

            if "from_source" in tool_yml:
                source_package = self.find_source(tool_yml["from_source"])
            else:
                source_package = None

            self.tools.append(ToolPackage(tool_yml, source_package))

    def load_packages_yml(self) -> None:
        with open(self.config["hbuild"]["packages_yml"]) as f:
            self.packages_yml = yaml.load(f, Loader=yaml.CLoader)["packages"]

    def load_packages(self) -> None:
        self.packages: list[Package] = []
        for package_yml in self.packages_yml:
            package_validator = Draft7Validator(self.schemas["package"], registry = self.registry)
            package_validator.validate(package_yml)

            if "from_source" in package_yml:
                source_package = self.find_source(package_yml["from_source"])
            else:
                source_package = None

            self.packages.append(Package(package_yml, source_package))

    def make_dirs(self):
        for source in self.sources:
            source.make_dirs(self.sources_dir)

        for tool in self.tools:
            tool.make_dirs(self.tools_dir, self.builds_dir)

        for package in self.packages:
            package.make_dirs(self.packages_dir, self.builds_dir)

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

    def find_implicit_source(self, name):
        for package in self.packages:
            if package.source_type == PackageSourceType.EXTERNAL_SOURCE:
                continue

            if package.source.name == name:
                return package.source

        for tool in self.tools:
            if tool.source_type == ToolSourceType.EXTERNAL_SOURCE:
                continue

            if tool.source.name == name:
                return tool.source

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

    def build_dep_tree(self):
        self.dep_dict= {}
        for source in self.sources:
            self.dep_dict[f"source[{source.name}]"] = source.deps()

        for tool in self.tools:
            self.dep_dict[tool.name] = tool.deps()
            for stage, stage_deps in tool.stage_deps.items():
                self.dep_dict[stage] = stage_deps

        for package in self.packages:
            self.dep_dict[package.name] = package.deps()
            for stage, stage_deps in tool.stage_deps.items():
                self.dep_dict[stage] = stage_deps

        # TODO: avoid two loops
        self.pkg_idxs = {}
        for pkg, deps in self.dep_dict.items():
            if pkg not in self.pkg_idxs:
                self.pkg_idxs[pkg] = self.dep_graph.add_node(pkg)

            for dep in deps:
                if dep not in self.pkg_idxs:
                    self.pkg_idxs[dep] = self.dep_graph.add_node(dep)

        for pkg, deps in self.dep_dict.items():
            pkg_idx = self.pkg_idxs[pkg]

            for dep in deps:
                dep_idx = self.pkg_idxs[dep]
                self.dep_graph.add_edge(pkg_idx, dep_idx, None)

        system_deps = {}
        for package in self.packages:
            if package.system_package is True:
                system_deps[package.name] = self.pkg_idxs[package.name]

        for pkg, deps in self.dep_dict.items():
            if pkg in system_deps:
                continue

            if pkg not in self.package_names:
                continue

            pkg_idx = self.pkg_idxs[pkg]
            for system_dep in system_deps.values():
                self.dep_graph.add_edge(pkg_idx, system_dep, None)

    def build_pkg_map(self):
        self.pkg_map = {}

        source_regex = re.compile(r'source\[(.*)\]')
        stage_regex = re.compile(r'(.*)\[(.*)\]')

        node_indices = self.dep_graph.node_indices()
        for node_idx in node_indices:
            node = self.dep_graph[node_idx]

            source_match = source_regex.fullmatch(node)
            stage_match = stage_regex.fullmatch(node)

            if bool(source_match):
                source_name = source_match.group(1)
                source_dep = self.find_source(source_name)
                if source_dep is not None:
                    self.pkg_map[node] = self.find_source(source_name)
                else:
                    source_dep = self.find_implicit_source(source_name)
                    if source_dep is None:
                        raise Exception(f"Unable to resolve source package {source_name}")

                    self.pkg_map[node] = source_dep
            elif bool(stage_match):
                master_name = stage_match.group(1)
                stage_name = stage_match.group(2)

                if self.is_tool(master_name):
                    self.pkg_map[node] = (self.find_tool(master_name), stage_name)
                else:
                    self.pkg_map[node] = (self.find_package(master_name), stage_name)
            else:
                if self.is_tool(node):
                    self.pkg_map[node] = self.find_tool(node)
                elif self.is_package(node):
                    self.pkg_map[node] = self.find_package(node)
                else:
                    self.pkg_map[node] = self.find_source(node)

    def build_root_map(self):
        self.roots: dict[str, int] = {}

        node_indices = self.dep_graph.node_indices()
        for node_idx in node_indices:
            node = self.dep_graph[node_idx]

            if self.dep_graph.in_degree(node_idx) == 0:
                self.roots[node] = node_idx

    def build_leaf_map(self):
        self.leaves: dict[str, int] = {}

        node_indices = self.dep_graph.node_indices()
        for node_idx in node_indices:
            node = self.dep_graph[node_idx]

            if self.dep_graph.out_degree(node_idx) == 0:
                self.leaves[node] = node_idx

    def resolve_deps(self):
        self.build_dep_tree()
        self.dep_graph, _ = rx.transitive_reduction(self.dep_graph)

        self.build_pkg_map()
        self.build_root_map()
        self.build_leaf_map()

    def format_node(self, node: str):
        if self.is_package(node):
            return f"[bright_green]{escape(node)}"
        elif self.is_tool(node):
            return f"[bright_magenta]{escape(node)}"
        else:
            return f"[bright_yellow]{escape(node)}"

    def print_node(self, node: str, node_idx: int, node_print_tree: Tree):
        if node_print_tree is None:
            node_print_tree = self.print_tree.add(self.format_node(node))

        for dep_idx in self.dep_graph.neighbors(node_idx):
            dep_node = self.dep_graph[dep_idx]
            dep_tree = node_print_tree.add(self.format_node(dep_node))

            self.print_node(dep_node, dep_idx, dep_tree)

    def show_deps(self):
        self.print_tree = Tree(
            "Installing Tree",
            guide_style="bold bright_blue"
        )

        node_indices = self.dep_graph.node_indices()
        roots = {}

        for node_idx in node_indices:
            node = self.dep_graph[node_idx]
            if self.dep_graph.in_degree(node_idx) == 0:
                roots[node] = node_idx

        for root_node, root_node_idx in roots.items():
            self.print_node(root_node, root_node_idx, None)

        rich_print(self.print_tree)

        # visual = graphviz_draw(self.dep_graph, node_attr_fn=lambda node: { "label": str(node) })
        # visual.show()

    def build_source(self, package: SourcePackage):
        package.prepare(self.sources_dir, self.system_prefix, self.patches_dir)
        package.regenerate(self.sources_dir, self.system_dir, self.system_prefix, self.system_target)

    def build_tool(self, package: ToolPackage, stage: str):
        if stage is not None:
            package.configure(self.sources_dir, self.builds_dir, self.tools_dir,
                self.system_prefix, self.system_target, self.system_dir, stage)

            package.compile(self.sources_dir, self.builds_dir, self.tools_dir,
                self.system_prefix, self.system_target, self.system_dir, stage)

            package.install(self.sources_dir, self.builds_dir, self.tools_dir,
                self.system_prefix, self.system_target, self.system_dir, stage)
        else:
            package.configure(self.sources_dir, self.builds_dir, self.tools_dir,
                self.system_prefix, self.system_target, self.system_dir, None)

            package.compile(self.sources_dir, self.builds_dir, self.tools_dir,
                self.system_prefix, self.system_target, self.system_dir, None)

            package.install(self.sources_dir, self.builds_dir, self.tools_dir,
                self.system_prefix, self.system_target, self.system_dir, None)

    def build_system(self, package: Package, stage: str):
        if stage is not None:
            package.configure(self.sources_dir, self.builds_dir, self.packages_dir,
                self.system_prefix, self.system_target, self.system_dir, stage)

            package.build(self.sources_dir, self.builds_dir, self.packages_dir,
                self.system_prefix, self.system_target, self.system_dir, stage)
        else:
            package.configure(self.sources_dir, self.builds_dir, self.packages_dir,
                self.system_prefix, self.system_target, self.system_dir, None)

            package.build(self.sources_dir, self.builds_dir, self.packages_dir,
                self.system_prefix, self.system_target, self.system_dir, None)
            
        package.copy_system(self.packages_dir, self.system_dir)
        package.make_deb(self.packages_dir, {dep: self.pkg_map[dep].version for dep in package.pkg_deps()})
            
    def build_package(self, name):
        print(f"Installing {name}")

        pkg_mapping = self.pkg_map[name]
        if isinstance(pkg_mapping, tuple):
            package, stage = pkg_mapping
        else:
            package, stage = pkg_mapping, None

        if isinstance(package, SourcePackage):
            self.build_source(package)
        elif isinstance(package, ToolPackage):
            self.build_tool(package, stage)
        else:
            self.build_system(package, stage)

    def build(self):
        self.make_dirs()

        self.install_order = rx.topological_sort(self.dep_graph)
        self.install_order = list(reversed(self.install_order))

        for pkg_idx in self.install_order:
            self.build_package(self.dep_graph[pkg_idx])

def main():
    hbuild = HBuild()

    hbuild.load_sources()
    hbuild.load_tools()
    hbuild.load_packages()

    hbuild.resolve_deps()
    hbuild.show_deps()

    hbuild.build()

if __name__ == "__main__":
    main()