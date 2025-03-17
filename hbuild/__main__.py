import json
import os
import re
import toml
import yaml

from dataclasses import field
from enum import Enum
from argparse_dataclass import dataclass as argclass
from argparse_dataclass import ArgumentParser

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

class HBuildState(int, Enum):
    CONFIGURED = 1
    BUILT = 2
    INSTALLED = 3

class HBuild:
    def __init__(self, selection, op):
        self.lock: dict[str: HBuildState] = {}

        self.load_config()
        self.load_lock()

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

        self.prefix_symlink = Path(self.system_dir, "prefix").resolve()

        if self.prefix_symlink.exists() is False:
            self.prefix_symlink.symlink_to(self.system_prefix, target_is_directory=True)

        self.system_targets = self.config["hbuild"]["system"]["targets"]

        self.dep_graph = rx.PyDiGraph(check_cycle = True)
        self.selection: list[str] = selection
        self.op: str = op

    def load_config(self) -> None:
        with open("config.toml") as f:
            self.config = toml.load(f)

    def load_lock(self) -> None:
        Path("hbuild.lock").touch(exist_ok=True)

        with open("hbuild.lock", "r+") as f:
            self.lock = json.load(f)

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

    def make_dirs(self, pkg_idxs):
       for pkg_idx in pkg_idxs:
            pkg_name = self.dep_graph[pkg_idx]
            pkg_mapping = self.pkg_map[pkg_name]
            if isinstance(pkg_mapping, tuple):
                package, _ = pkg_mapping
            else:
                package = pkg_mapping

            if isinstance(package, SourcePackage):
                package.make_dirs(self.sources_dir)
            elif isinstance(package, ToolPackage):
                package.make_dirs(self.tools_dir, self.builds_dir)
            elif isinstance(package, Package):
                package.make_dirs(self.packages_dir, self.builds_dir)

    def clean_dirs(self, pkg_idxs):
       for pkg_idx in pkg_idxs:
            pkg_name = self.dep_graph[pkg_idx]
            pkg_mapping = self.pkg_map[pkg_name]
            if isinstance(pkg_mapping, tuple):
                package, _ = pkg_mapping
            else:
                package = pkg_mapping

            if isinstance(package, SourcePackage):
                package.clean_dirs(self.sources_dir)
            elif isinstance(package, ToolPackage):
                package.clean_dirs(self.tools_dir, self.builds_dir)
            elif isinstance(package, Package):
                package.clean_dirs(self.packages_dir, self.builds_dir, self.system_dir)

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
        self.dep_dict: dict[str: list[str]] = {}
        self.pkg_idxs = {}

        for source in self.sources:
            source_fmt_name = f"source[{source.name}]"

            self.dep_dict[source_fmt_name] = source.deps()
            if source_fmt_name not in self.pkg_idxs:
                self.pkg_idxs[source_fmt_name] = self.dep_graph.add_node(source_fmt_name)

            for dep in source.deps():
                if dep not in self.pkg_idxs:
                    self.pkg_idxs[dep] = self.dep_graph.add_node(dep)

        for tool in self.tools:
            self.dep_dict[tool.name] = tool.deps()

            if tool.name not in self.pkg_idxs:
                self.pkg_idxs[tool.name] = self.dep_graph.add_node(tool.name)

            for dep in tool.deps():
                if dep not in self.pkg_idxs:
                    self.pkg_idxs[dep] = self.dep_graph.add_node(dep)

            for stage, stage_deps in tool.stage_deps.items():
                if stage not in self.pkg_idxs:
                    self.pkg_idxs[stage] = self.dep_graph.add_node(stage)
                    self.dep_dict[tool.name] = [*self.dep_dict[tool.name], stage]

                self.dep_dict[stage] = stage_deps
                for dep in stage_deps:
                    if dep not in self.pkg_idxs:
                        self.pkg_idxs[dep] = self.dep_graph.add_node(dep)

        system_deps = {}
        no_deps = []

        for package in self.packages:
            self.dep_dict[package.name] = package.deps()

            if package.name not in self.pkg_idxs:
                self.pkg_idxs[package.name] = self.dep_graph.add_node(package.name)

            if package.system_package is True and package.name not in system_deps:
                system_deps[package.name] = self.pkg_idxs[package.name]
            
            if package.no_deps is True:
                no_deps.append(package.name)

            for dep in package.deps():
                if dep not in self.pkg_idxs:
                    self.pkg_idxs[dep] = self.dep_graph.add_node(dep)

            for stage, stage_deps in package.stage_deps.items():
                if stage not in self.pkg_idxs:
                    self.pkg_idxs[stage] = self.dep_graph.add_node(stage)
                    self.dep_dict[package.name] = [*self.dep_dict[package.name], stage]

                self.dep_dict[stage] = stage_deps
                for dep in stage_deps:
                    if dep not in self.pkg_idxs:
                        self.pkg_idxs[dep] = self.dep_graph.add_node(dep)
                
        # TODO: avoid two loops

        for pkg, deps in self.dep_dict.items():
            pkg_idx = self.pkg_idxs[pkg]

            for dep in deps:
                if dep not in self.pkg_idxs:
                    raise Exception(f"Unable to resolve dependency {pkg} -> {dep}")

                dep_idx = self.pkg_idxs[dep]
                self.dep_graph.add_edge(pkg_idx, dep_idx, None)
            
            if pkg not in no_deps and pkg not in system_deps and pkg in self.package_names:
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

    def resolve_deps(self):
        self.build_dep_tree()
        if len(self.selection) > 0:
            roots = []
            descendants = []
            for package in self.selection:
                roots.append(self.pkg_idxs[package])
                root_descendants = rx.descendants(self.dep_graph, self.pkg_idxs[package])

                for descendant in root_descendants:
                    if descendant not in descendants:
                        descendants.append(descendant)

            self.dep_graph = self.dep_graph.subgraph([*descendants, *roots])

        self.dep_graph, _ = rx.transitive_reduction(self.dep_graph)
        self.build_pkg_map()

        self.install_order = rx.topological_sort(self.dep_graph)
        self.install_order = list(reversed(self.install_order))

        if self.op != "clean" or len(self.selection) > 0:
            self.install_order = [pkg_idx for pkg_idx in self.install_order if self.dep_graph[pkg_idx] not in self.lock or self.lock[self.dep_graph[pkg_idx]] != HBuildState.INSTALLED or self.dep_graph[pkg_idx] in self.selection]

    def format_node(self, node: str):
        if self.op == "clean" and len(self.selection) == 0:
            return f"[bright_green]{escape(node)}"
        else:
            if node not in self.lock or self.lock[node] != HBuildState.INSTALLED or node in self.selection:
                return f"[bright_green]{escape(node)}"
            else:
                return f"[gray]{escape(node)}"

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

        visual = graphviz_draw(self.dep_graph, node_attr_fn=lambda node: { "label": str(node) })
        visual.show()

    def build_source(self, package: SourcePackage):
        source_name = f"source[{package.name}]"
        if self.has_installed(source_name) is False:
            package.prepare(self.sources_dir, self.system_prefix, self.patches_dir)
            os.sync()

            package.regenerate(self.sources_dir, self.system_dir, self.system_prefix, self.system_targets)
            os.sync()

            self.mark_installed(source_name)

    def build_tool(self, package: ToolPackage, stage_name: str):
        stage = package.find_stage(stage_name)

        if self.has_configured(package.name) is False:
            package.configure(self.sources_dir, self.builds_dir, self.tools_dir,
                self.system_prefix, self.system_targets, self.system_dir)
            os.sync()
            self.mark_configured(package.name)

        full_stage_name = f"{package.name}[{stage_name}]"
        if stage is not None:
            if self.has_built(full_stage_name) is False:
                package.compile(self.sources_dir, self.builds_dir, self.tools_dir,
                    self.system_prefix, self.system_targets, self.system_dir, stage)
                os.sync()
                self.mark_built(full_stage_name)

            if self.has_installed(full_stage_name) is False:
                package.install(self.sources_dir, self.builds_dir, self.tools_dir,
                    self.system_prefix, self.system_targets, self.system_dir, stage)
                os.sync()
                self.mark_installed(full_stage_name)
        else:
            if self.has_built(package.name) is False:
                package.compile(self.sources_dir, self.builds_dir, self.tools_dir,
                    self.system_prefix, self.system_targets, self.system_dir, None)
                os.sync()
                self.mark_built(package.name)

            if self.has_installed(package.name) is False:
                package.install(self.sources_dir, self.builds_dir, self.tools_dir,
                    self.system_prefix, self.system_targets, self.system_dir, None)
                os.sync()
                self.mark_installed(package.name)
            
    def build_system(self, package: Package, stage_name: str):
        stage = package.find_stage(stage_name)

        if self.has_configured(package.name) is False:
            package.configure(self.sources_dir, self.builds_dir, self.packages_dir,
                self.system_prefix, self.system_targets, self.system_dir)
            os.sync()
            self.mark_configured(package.name)

        full_stage_name = f"{package.name}[{stage_name}]"
        if stage is not None and self.has_built(full_stage_name) is False:
            package.build(self.sources_dir, self.builds_dir, self.packages_dir,
                self.system_prefix, self.system_targets, self.system_dir, stage)
            os.sync()
            self.mark_built(full_stage_name)
        elif self.has_built(package.name) is False:
            package.build(self.sources_dir, self.builds_dir, self.packages_dir,
                self.system_prefix, self.system_targets, self.system_dir, None)
            os.sync()
            self.mark_built(package.name)

    def build_deb(self, package: Package):
        if self.has_installed(package.name) is False:
            package.copy_system(self.packages_dir, self.system_dir)
            os.sync()

            package.make_deb(self.packages_dir, {dep: self.pkg_map[dep].version for dep in package.pkg_deps()})
            os.sync()

            self.mark_installed(package.name)

    def build_package(self, name):
        print(f"Installing {name}")

        pkg_mapping = self.pkg_map[name]
        if isinstance(pkg_mapping, tuple):
            package, stage_name = pkg_mapping
        else:
            package, stage_name = pkg_mapping, None

        if isinstance(package, SourcePackage):
            self.build_source(package)
        elif isinstance(package, ToolPackage):
            self.build_tool(package, stage_name)
        elif isinstance(package, Package):
            self.build_system(package, stage_name)
            self.build_deb(package)

    def build(self):
        self.make_dirs(self.install_order)
        for pkg_idx in self.install_order:
            self.build_package(self.dep_graph[pkg_idx])
            self.commit()
    
    def install(self):
        for pkg_idx in self.install_order:
            pkg_mapping = self.pkg_map[self.dep_graph[pkg_idx]]
            if isinstance(pkg_mapping, tuple):
                package = pkg_mapping
            else:
                package, _ = pkg_mapping, None

            if isinstance(package, Package):
                package.copy_system(self.packages_dir, self.system_dir)
            else:
                if package.name in self.selection:
                    rich_print("[yellow] WARN: Source or tool package passed to hbuild.install")

    def clean(self):
        self.clean_dirs(self.install_order)
        for pkg_idx in self.install_order:
            self.unmark_configured(self.dep_graph[pkg_idx])

    def package(self):
        for pkg_idx in self.install_order:
            pkg_mapping = self.pkg_map[self.dep_graph[pkg_idx]]
            if isinstance(pkg_mapping, tuple):
                package = pkg_mapping
            else:
                package, _ = pkg_mapping, None

            if isinstance(package, Package):
                self.build_deb(package)
            else:
                rich_print("[yellow] WARN: Source or tool package passed to hbuild.package")

    def has_configured(self, pkg_name):
        if pkg_name in self.lock and self.lock[pkg_name] == HBuildState.CONFIGURED:
            return True
        return False

    def has_built(self, pkg_name):
        if pkg_name in self.lock and self.lock[pkg_name] == HBuildState.BUILT:
            return True
        return False

    def has_installed(self, pkg_name):
        if pkg_name in self.lock and self.lock[pkg_name] == HBuildState.INSTALLED:
            return True
        return False

    def mark_configured(self, pkg_name):
        self.lock[pkg_name] = HBuildState.CONFIGURED

    def unmark_configured(self, pkg_name):
        if pkg_name in self.lock:
            del self.lock[pkg_name]

    def mark_built(self, pkg_name):
        self.lock[pkg_name] = HBuildState.BUILT

    def unmark_built(self, pkg_name):
        if pkg_name in self.lock:
            self.lock[pkg_name] = HBuildState.CONFIGURED

    def mark_installed(self, pkg_name):
        self.lock[pkg_name] = HBuildState.INSTALLED

    def unmark_installed(self, pkg_name):
        if pkg_name in self.lock:
            self.lock[pkg_name] = HBuildState.BUILT

    def commit(self):
        with open("hbuild.lock", "w+") as f:
            json.dump(self.lock, f)

@argclass
class HBuildArgs:
    op: str = field(metadata=dict(args=["op"], choices=["build","install", "clean", "package", "show"]))
    selection: list[str] = field(default_factory=lambda: [], metadata=dict(nargs='*', args=["selection"]))

def main():
    parser = ArgumentParser(HBuildArgs)
    args = parser.parse_args()

    hbuild = HBuild(args.selection, args.op)

    hbuild.load_sources()
    hbuild.load_tools()
    hbuild.load_packages()

    hbuild.resolve_deps()
    hbuild.show_deps()

    if args.op == "build":
        hbuild.build()
        hbuild.commit()
    elif args.op == "install":
        hbuild.install()
    elif args.op == "clean":
        hbuild.clean()
        hbuild.commit()
    elif args.op == "package":
        hbuild.package()
    elif args.op == "show":
        pass

if __name__ == "__main__":
    main()