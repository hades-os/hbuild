import re
from enum import Enum

import rustworkx as rx
from rustworkx import PyDiGraph
from rustworkx.visualization.graphviz import graphviz_draw

from .package import Package
from .registry import HPackageRegistry
from .source import SourcePackage
from .stage import Stage
from .tool import ToolPackage

import pika as mq

def format_lookup_name(package: SourcePackage | ToolPackage | Package | Stage) -> str:
    if isinstance(package, SourcePackage):
        return f"source[{package.name}]"
    elif isinstance(package, Stage):
        return f"{package.package_name}[{package.name}]"
    else:
        return package.name

class HBuildOperation(Enum):
    BUILD = 1
    INSTALL = 2
    CLEAN = 3
    PACKAGE = 4

class HPackageNode():
    def __init__(self, index: int, package: SourcePackage | ToolPackage | Package | Stage,
                 deps: list[str]):
        self.name = package.name
        self.lookup_name = format_lookup_name(package)
        self.index = index
        self.package = package
        self.deps = deps
    def __repr__(self):
        return self.lookup_name
    def __str__(self):
        return self.lookup_name

class HBuildDispatch():
    def __init__(self):
        self.registry = HPackageRegistry()

        self.registry.load_sources()
        self.registry.load_tools()
        self.registry.load_packages()

        self.node_indices: dict[int | str, HPackageNode] = {}
        self.graph = rx.PyDiGraph()

        self.build_graph()

    def add_node(self, package: SourcePackage | ToolPackage | Package | Stage, deps: list[str]):
        lookup_name = format_lookup_name(package)
        node = HPackageNode(0, package, [])
        index = self.graph.add_node(node)
        self.node_indices[index] = node
        self.node_indices[lookup_name] = node
        self.graph[index].index = index

    def lookup(self, name: str) -> Package | ToolPackage | SourcePackage | Stage | None:
        source_try = self.registry.find_source(name)
        if source_try is not None:
            return source_try
        elif (source_try := self.registry.find_tool(name)) is not None:
            return source_try
        elif (source_try := self.registry.find_package(name)) is not None:
            return source_try
        elif (matches := re.match('(.+)\\[(.+)]', name)) is not None:
            parent = self.lookup(matches.group(1))
            return parent.find_stage(matches.group(2))
        else:
            return None

    def build_graph(self):
        dep_dict: dict[str, list[str]] = {}

        for source in self.registry.sources:
            lookup_name = format_lookup_name(source)
            dep_dict[lookup_name] = source.deps()

            if lookup_name not in self.node_indices:
                self.add_node(source, source.deps())

            for dep in source.deps():
                if dep not in self.node_indices:
                    dep_package = self.lookup(dep)
                    if dep_package is None:
                        raise Exception(f"Unable to find dependency {dep.name} for source {source.name}")
                    self.add_node(dep_package, dep_package.deps())

        for tool in self.registry.tools:
            lookup_name = format_lookup_name(tool)
            dep_dict[tool.name] = tool.deps()

            if tool.name not in self.node_indices:
                self.add_node(tool, tool.deps())

            for dep in tool.deps():
                if dep not in self.node_indices:
                    dep_package = self.lookup(dep)
                    if dep_package is None:
                        raise Exception(f"Unable to find dependency {dep.name} for tool {tool.name}")
                    self.add_node(dep_package, dep_package.deps())

            for stage, stage_deps in tool.stage_deps.items():
                if stage not in self.node_indices:
                    stage_package = self.lookup(stage)
                    if stage_package is None:
                        raise Exception(f"Unable to find stage {stage.name}")
                    self.add_node(stage_package, stage_deps)
                    dep_dict[tool.name] = [*dep_dict[tool.name], stage]

                dep_dict[stage] = stage_deps
                for dep in stage_deps:
                    if dep not in self.node_indices:
                        dep_package = self.lookup(dep)
                        if dep_package is None:
                            raise Exception(f"Unable to find dependency {dep.name} for stage {stage.name}")
                        self.add_node(dep_package, dep_package.deps())

        system_deps = {}
        no_deps = []

        for package in self.registry.packages:
            dep_dict[package.name] = package.deps()

            if package.name not in self.node_indices:
                self.add_node(package, package.deps())

            if package.system_package is True and package.name not in system_deps:
                system_deps[package.name] = self.node_indices[package.name]

            if package.no_deps:
                no_deps.append(package.name)

            for dep in package.deps():
                if dep not in self.node_indices:
                    dep_package = self.lookup(dep)
                    if dep_package is None:
                        raise Exception(f"Unable to find dependency {dep.name} for package {package.name}")
                    self.add_node(dep_package, dep_package.deps())

            for stage, stage_deps in package.stage_deps.items():
                if stage not in self.node_indices:
                    stage_package = self.lookup(stage)
                    if stage_package is None:
                        raise Exception(f"Unable to find stage {stage.name}")
                    self.add_node(stage_package, stage_deps)
                    dep_dict[package.name] = [*dep_dict[package.name], stage]

                dep_dict[stage] = stage_deps
                for dep in stage_deps:
                    if dep not in self.node_indices:
                        dep_package = self.lookup(dep)
                        if dep_package is None:
                            raise Exception(f"Unable to find dependency {dep.name} for stage {stage.name}")
                        self.add_node(dep_package, dep_package.deps())

        # TODO: avoid two loops

        for pkg, deps in dep_dict.items():
            pkg_idx = self.node_indices[pkg].index

            for dep in deps:
                if dep not in self.node_indices:
                    raise Exception(f"Unable to resolve dependency {pkg} -> {dep}")

                dep_idx = self.node_indices[dep].index
                self.graph.add_edge(pkg_idx, dep_idx, None)

            if pkg not in no_deps and pkg not in system_deps and pkg in self.registry.package_names:
                for system_dep in system_deps.values():
                    self.graph.add_edge(pkg_idx, system_dep.index, None)

    def build_subgraph(self, selection) -> tuple[PyDiGraph, dict[int, int]]:
        subgraph: rx.PyDiGraph | None = None
        nodemap: dict[int, int] = {}
        if len(selection) > 0:
            roots = []
            descendants = []
            for package in selection:
                root_index = self.node_indices[package].index

                roots.append(root_index)
                root_descendants = rx.descendants(self.graph, root_index)

                for descendant in root_descendants:
                    if descendant not in descendants:
                        descendants.append(descendant)

            (subgraph, nodemap) = self.graph.subgraph_with_nodemap([*descendants, *roots])

        subgraph, tr_nodemap = rx.transitive_reduction(subgraph)

        # nodemap: new nodes -> old nodes
        # tr_nodemap: new nodes -> reduced nodes
        # full_nodemap: reduced nodes -> old nodes
        full_nodemap = {tr_nodemap[k] : v for k, v in nodemap.items()}

        return subgraph, full_nodemap

    def build_indices(self, order_graph: rx.PyDiGraph) -> list[int]:
        install_order = rx.topological_sort(order_graph)
        install_order = list(reversed(install_order))

        return install_order

    def consume(self, channel, method, properties, raw_body):
        body = raw_body.decode("utf-8")
        objects = body.split(":")
        operation = objects[0]
        if operation == "build":
            requested_packages = objects[1].split(",")
            subgraph, full_nodemap = self.build_subgraph(requested_packages)

            build_indices = self.build_indices(subgraph)
            build_order = [str(self.graph[full_nodemap[idx]]) for idx in build_indices]

            self.channel.basic_publish(exchange='',
                                       routing_key='runners',
                                       body=f"execute:{','.join(build_order)}")
        elif operation == "log":
            package_namels    = objects[1]
            stage_name = objects[2]
            log = objects[3]

            print(package_name, stage_name)

    def run_server(self):
        credentials = mq.PlainCredentials('mq', 'mq')
        connection = mq.BlockingConnection(mq.ConnectionParameters('localhost',
                                                                   5672,
                                                                   credentials=credentials))
        self.channel = connection.channel()
        self.channel.queue_declare(queue = 'dispatch')
        for package in self.registry.packages + self.registry.tools + self.registry.sources:
            self.channel.queue_declare(queue=format_lookup_name(package))
            self.channel.basic_consume(queue=format_lookup_name(package), on_message_callback=self.consume, auto_ack=True)

        self.channel.basic_consume(queue = 'dispatch', on_message_callback = self.consume, auto_ack=True)
        self.channel.start_consuming()