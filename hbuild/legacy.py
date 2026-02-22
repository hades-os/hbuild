import asyncio
import json
import os
import re
import toml
import threading
import yaml

from bubus import EventBus, BaseEvent

from classy_fastapi import Routable, get, delete, post

from dataclasses import field
from enum import Enum
from argparse_dataclass import dataclass as argclass
from argparse_dataclass import ArgumentParser

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette import EventSourceResponse, ServerSentEvent

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
from .tool import ToolPackage
from .package import Package
from .stage import Stage

from .models import HBuildState, BuildOrder, ResolveOrder

class HBuild(Routable):
    def __init__(self):
        super().__init__()
        self.bus = EventBus()

        self.lock: dict[str: HBuildState] = {}

        self.load_config()
        self.load_lock()

        self.registry = Registry()
        self.sources: list[SourcePackage] = []
        self.tools: list[ToolPackage] = []
        self.packages: list[Package] = []

        self.source_linkages: dict[str, list[str]] = {}
        self.commit_lock = threading.Lock()
        self.build_locks: dict[str, threading.Lock]  = {}

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

        self.dep_graph = rx.PyDiGraph(check_cycle = True)

        self.load_schemas()
        self.load_pkgsrc_dir()
        self.link_sources()

        self.build_dep_tree()
        self.build_pkg_map()

        self.create_locks()

    def load_config(self) -> None:
        with open("config.toml") as f:
            self.config = toml.load(f)

    def load_lock(self) -> None:
        Path("hbuild.lock").write_text("{}")

        with open("hbuild.lock", "r+") as f:
            self.lock = json.load(f)

    def load_schema(self, schema_file: str) -> object:
        with open(schema_file) as f:
            schema_json = json.load(f)
            return (schema_json["$id"], schema_json)

    def load_schemas(self) -> None:
        self.schemas = {}
        for dir, _, files in os.walk(self.config["hbuild"]["schema_dir"]):
            for file in files:
                schema_path = os.path.join(dir, file)
                schema_id, schema_json = self.load_schema(schema_path)
                schema_name = schema_id.split('/')[4]

                schema = DRAFT7.create_resource(schema_json)

                self.registry = self.registry.with_resource(schema_id, schema)
                self.schemas[schema_name] = schema_json

    def link_source(self, package_name, source_name):
        if source_name in self.source_linkages.keys():
            self.source_linkages[source_name].append(package_name)
        else:
            self.source_linkages[source_name] = [package_name]

    def link_sources(self):
        for source_name, pkg_names in self.source_linkages.items():
            for pkg_name in pkg_names:
                tool = self.find_tool(pkg_name)
                if tool is None:
                    package = self.find_package(pkg_name)
                    if package is None:
                        print(package, self.packages)
                        raise Exception(f"Unable to resolve package {pkg_name}")
                    source_package = self.find_source(source_name)
                    if source_package is None:
                        raise Exception(f"Unable to resolve source {source_name}")
                    package.link_source(source_package)
                else:
                    source_package = self.find_source(source_name)
                    if source_package is None:
                        raise Exception(f"Unable to resolve source {source_name}")

                    tool.link_source(source_package)

    def load_pkgsrc(self, pkgsrc_file: str) -> object:
        with open(pkgsrc_file) as f:
            return yaml.load(f, Loader=yaml.CLoader)

    def load_pkgsrc_dir(self) -> None:
        for dir, _, files in os.walk(self.config["hbuild"]["pkgsrc_dir"]):
            for file in files:
                pkgsrc_path = os.path.join(dir, file)
                pkgsrc_yml = self.load_pkgsrc(pkgsrc_path)

                pkgsrc_validator = Draft7Validator(self.schemas["pkgsrc"], registry=self.registry)
                pkgsrc_validator.validate(pkgsrc_yml)

                if "source" in pkgsrc_yml:
                    source_validator = Draft7Validator(self.schemas["source"], registry = self.registry)
                    source_validator.validate(pkgsrc_yml["source"])

                    self.sources.append(SourcePackage(
                        pkgsrc_yml["source"],
                        self.logs_dir,
                        self.sources_dir,
                        self.patches_dir,

                        self.system_targets,
                        self.system_prefix,
                        self.system_root
                    ))

                if "tools" in pkgsrc_yml:
                    for tool_yml in pkgsrc_yml["tools"]:
                        tool_validator = Draft7Validator(self.schemas["tool"], registry = self.registry)
                        tool_validator.validate(tool_yml)

                        tool_package = ToolPackage(
                            tool_yml,
                            self.logs_dir,
                            self.sources_dir,
                            self.builds_dir,

                            self.tools_dir,
                            self.works_dir,

                            self.system_targets,
                            self.system_prefix,
                            self.system_root
                        )

                        self.link_source(tool_package.name, tool_package.source_name)
                        self.tools.append(tool_package)
                if "packages" in pkgsrc_yml:
                    for package_yml in pkgsrc_yml["packages"]:
                        package_validator = Draft7Validator(self.schemas["package"], registry = self.registry)
                        package_validator.validate(package_yml)

                        package = Package(
                            package_yml,
                            self.logs_dir,
                            self.sources_dir,
                            self.builds_dir,

                            self.packages_dir,
                            self.works_dir,

                            self.system_targets,
                            self.system_prefix,
                            self.system_root
                        )

                        self.link_source(package.name, package.source_name)
                        self.packages.append(package)

    def make_dir(self, package: Package | ToolPackage | SourcePackage):
        package.make_dirs()

    def make_container(self, package: Package | ToolPackage | SourcePackage):
        package.make_container()

    def tidy(self, install_order):
       for pkg_idx in install_order:
            pkg_name = self.dep_graph[pkg_idx]
            pkg_mapping = self.pkg_map[pkg_name]
            if isinstance(pkg_mapping, tuple):
                package, _ = pkg_mapping
            else:
                package = pkg_mapping

            package.tidy()



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

    def build_dep_tree(self):
        self.dep_dict: dict[str, list[str]] = {}
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
                    raise Exception(f"Unable to resolve source package {source_name}")
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
                    raise Exception(f"Unable to resolve package {node}")


    def create_locks(self):
        for _, pkg_mapping in self.pkg_map.items():
            if isinstance(pkg_mapping, tuple):
                package, _ = pkg_mapping
            else:
                package = pkg_mapping

            self.build_locks[package.name] = threading.Lock()
    def resolve_deps(self, selection, op):
        dep_graph = self.dep_graph
        if len(selection) > 0:
            roots = []
            descendants = []
            for package in selection:
                roots.append(self.pkg_idxs[package])
                root_descendants = rx.descendants(self.dep_graph, self.pkg_idxs[package])

                for descendant in root_descendants:
                    if descendant not in descendants:
                        descendants.append(descendant)

            dep_graph = dep_graph.subgraph([*descendants, *roots])

        dep_graph, _ = rx.transitive_reduction(dep_graph)
        install_order = rx.topological_sort(dep_graph)
        install_order = list(reversed(install_order))

        if op != "clean" or len(selection) > 0:
            with self.commit_lock:
                install_order = [pkg_idx for pkg_idx in install_order if dep_graph[pkg_idx] not in self.lock or self.lock[dep_graph[pkg_idx]] != HBuildState.INSTALLED or dep_graph[pkg_idx] in selection]

        return install_order, dep_graph

    def format_node(self, node: str, selection, op):
        if op == "clean" and len(selection) == 0:
            return f"[bright_green]{escape(node)}"
        else:
            if node not in self.lock or self.lock[node] != HBuildState.INSTALLED or node in selection:
                return f"[bright_green]{escape(node)}"
            else:
                return f"[gray]{escape(node)}"

    def print_node(self, node: str, node_idx: int, node_print_tree: Tree, selection, op, dep_graph):
        if node_print_tree is None:
            node_print_tree = self.print_tree.add(self.format_node(node, selection, op))

        for dep_idx in dep_graph.neighbors(node_idx):
            dep_node = dep_graph[dep_idx]
            dep_tree = node_print_tree.add(self.format_node(dep_node, selection, op))

            self.print_node(dep_node, dep_idx, dep_tree, selection, op, dep_graph)

    def show_deps(self, selection, op, dep_graph):
        self.print_tree = Tree(
            "Installing Tree",
            guide_style="bold bright_blue"
        )

        node_indices = dep_graph.node_indices()
        roots = {}

        for node_idx in node_indices:
            node = dep_graph[node_idx]
            if dep_graph.in_degree(node_idx) == 0:
                roots[node] = node_idx

        for root_node, root_node_idx in roots.items():
            self.print_node(root_node, root_node_idx, None, selection, op, dep_graph)

        rich_print(self.print_tree)


    def has_configured(self, pkg_name):
        with self.commit_lock:
            if pkg_name in self.lock and self.lock[pkg_name] == HBuildState.CONFIGURED:
                return True
            return False

    def has_built(self, pkg_name):
        with self.commit_lock:
            if pkg_name in self.lock and self.lock[pkg_name] == HBuildState.BUILT:
                return True
            return False

    def has_installed(self, pkg_name):
        with self.commit_lock:
            if pkg_name in self.lock and self.lock[pkg_name] == HBuildState.INSTALLED:
                return True
            return False

    def mark_configured(self, pkg_name):
        with self.commit_lock:
            self.lock[pkg_name] = HBuildState.CONFIGURED

    def unmark_configured(self, pkg_name):
        with self.commit_lock:
            if pkg_name in self.lock:
                del self.lock[pkg_name]

    def mark_built(self, pkg_name):
        with self.commit_lock:
            self.lock[pkg_name] = HBuildState.BUILT

    def unmark_built(self, pkg_name):
        with self.commit_lock:
            if pkg_name in self.lock:
                self.lock[pkg_name] = HBuildState.CONFIGURED

    def mark_installed(self, pkg_name):
        with self.commit_lock:
            self.lock[pkg_name] = HBuildState.INSTALLED

    def unmark_installed(self, pkg_name):
        with self.commit_lock:
            if pkg_name in self.lock:
                self.lock[pkg_name] = HBuildState.BUILT

    def commit(self):
        with open("hbuild.lock", "w+") as f:
            json.dump(self.lock, f)

    def process(self, op, install_order, dep_graph):
        # node indices are not preserved, so we have to map them back
        true_install_order = [self.pkg_idxs[dep_graph[idx]] for idx in install_order]
        try:
            if op == "build":
                hbuild.build(true_install_order)
                hbuild.commit()
            elif op == "install":
                hbuild.install(true_install_order)
            elif op == "clean":
                hbuild.clean(true_install_order)
                hbuild.commit()
            elif op == "package":
                hbuild.package(true_install_order)
        except Exception as err:
            raise err
        finally:
            hbuild.tidy(install_order)



@argclass
class HBuildArgs:
    op: str = field(metadata=dict(args=["op"], choices=["build","install", "clean", "package", "show", "server"]))
    selection: list[str] = field(default_factory=lambda: [], metadata=dict(nargs='*', args=["selection"]))

def main():
    parser = ArgumentParser(HBuildArgs)
    args = parser.parse_args()

    hbuild = HBuild()
    install_order, dep_graph = hbuild.resolve_deps(args.selection, args.op)
    hbuild.show_deps(args.selection, args.op, dep_graph)

    true_install_order = [hbuild.pkg_idxs[dep_graph[idx]] for idx in install_order]
    try:
        if args.op == "build":
            hbuild.build(true_install_order)
            hbuild.commit()
        elif args.op == "install":
            hbuild.install(true_install_order)
        elif args.op == "clean":
            hbuild.clean(true_install_order)
            hbuild.commit()
        elif args.op == "package":
            hbuild.package(true_install_order)
        elif args.op == "show":
            pass
        elif args.op == "server":
            pass
    except Exception as err:
        raise err
    finally:
        hbuild.tidy(true_install_order)
