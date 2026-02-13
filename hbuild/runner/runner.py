import queue
import random
import re
import time
from queue import Queue
from threading import Thread

import pymysql

from hbuild.registry import HPackageRegistry

import pika as mq

from hbuild.source import SourcePackage
from hbuild.sql import HBuildLog
from hbuild.stage import Stage
from hbuild.tool import ToolPackage
from hbuild.package import Package

import os

def format_lookup_name(package: SourcePackage | ToolPackage | Package | Stage) -> str:
    if isinstance(package, SourcePackage):
        return f"source[{package.name}]"
    elif isinstance(package, Stage):
        return f"{package.package_name}[{package.name}]"
    else:
        return package.name

class HBuildJob():
    def __init__(self, requested_packages: list[Package | ToolPackage | SourcePackage | Stage]):
        self.requested_packages = requested_packages

class HBuildRunner():
    def __init__(self):
        self.registry = HPackageRegistry()
        self.queue = Queue()
        self.name = f"runner-{random.randint(0, 1000)}"

        self.credentials = mq.PlainCredentials('mq', 'mq')
        self.connection = mq.BlockingConnection(mq.ConnectionParameters('localhost',
                                                                   5672,
                                                                   credentials=self.credentials))
        self.channel = self.connection.channel()
        self.channel.queue_declare(queue = 'runners')
        self.channel.basic_consume(queue = 'runners', on_message_callback = self.consume, auto_ack=True)

        self.sql_conn = pymysql.connect(host='localhost',
                                     user='root',
                                     password='sql',
                                     database='sql',
                                     cursorclass=pymysql.cursors.DictCursor)

        self.thread = Thread(target = self.execute_jobs)
        self.thread.start()

    def lookup(self, name: str) -> Package | ToolPackage | SourcePackage | Stage | None:
        if (matches := re.match('source\\[(.+)]', name)) is not None:
            name = matches.group(1)
            source_try = self.registry.find_source(name)
            if source_try is not None:
                return source_try
            else:
                raise Exception(f"Unknown source name: {name}, sent to runner (accident?)")
        elif (source_try := self.registry.find_tool(name)) is not None:
            return source_try
        elif (source_try := self.registry.find_package(name)) is not None:
            return source_try
        elif (matches := re.match('(.+)\\[(.+)]', name)) is not None:
            parent = self.lookup(matches.group(1))
            return parent.find_stage(matches.group(2))
        else:
            raise Exception(f"Unknown package name: {name}, sent to runner (accident?)")

    def run_server(self):
        self.channel.start_consuming()

    def consume(self, channel, method, properties, raw_body):
        body = raw_body.decode("utf-8")
        objects = body.split(":")
        operation =  objects[0]
        if operation == "execute":
            requested_packages = objects[1].split(",")
            resolved_packages = [self.lookup(name) for name in requested_packages]
            self.queue.put(HBuildJob(resolved_packages))

    def execute_jobs(self):
        while True:
            try:
                next_job: HBuildJob = self.queue.get()
                HBuildLog.insert_history(self.sql_conn, self.name, [format_lookup_name(p) for p in next_job.requested_packages])
                for resolved_package in next_job.requested_packages:
                    if isinstance(resolved_package, Stage):
                        self.build_package(resolved_package.package, resolved_package.name)
                    else:
                        self.build_package(resolved_package, None)
            except queue.Empty:
                pass
            time.sleep(1)

    def make_dir(self, package: Package | ToolPackage | SourcePackage):
        package.make_dirs()

    def make_container(self, package: Package | ToolPackage | SourcePackage):
        package.make_container()

    def build_source(self, package: SourcePackage):
        prepare_resp = package.prepare()
        if isinstance(prepare_resp, Exception):
            print(f"Failed to prepare source {package.name}, exit message: {prepare_resp}")
            return
        os.sync()

        regenerate_resp = package.regenerate()
        if isinstance(regenerate_resp, Exception):
            print(f"Failed to regenerate source {package.name}, exit message: {regenerate_resp}")
            return
        os.sync()

        return prepare_resp, regenerate_resp

    def build_tool(self, package: ToolPackage, stage_name: str):
        stage = package.find_stage(stage_name)

        configure_resp = package.configure()
        if isinstance(configure_resp, Exception):
            print(f"Failed to configure {package.name}, exit message: {configure_resp}")
            return

        os.sync()

        if stage is not None:
            compile_resp = package.compile(stage)
            if isinstance(compile_resp, Exception):
                print(f"Failed to build {package.name}[{stage.name}], exit message: {compile_resp}")
                return

            os.sync()

            install_resp = package.install(stage)
            if isinstance(install_resp, Exception):
                print(f"Failed to install {package.name}[{stage.name}], exit message: {install_resp}")
                return

            os.sync()

            package.copy_tool()
            os.sync()

            return configure_resp, compile_resp, install_resp
        else:
            compile_resp = package.compile(None)
            if isinstance(compile_resp, Exception):
                print(f"Failed to build {package.name}, exit message: {compile_resp}")
                return

            os.sync()
            install_resp = package.install(None)
            if isinstance(install_resp, Exception):
                print(f"Failed to install {package.name}, exit message: {install_resp}")
                return

            os.sync()

            package.copy_tool()
            os.sync()

            return configure_resp, compile_resp, install_resp

    def build_system(self, package: Package, stage_name: str):
        stage = package.find_stage(stage_name)

        configure_resp = package.configure()
        if isinstance(configure_resp, Exception):
            print(f"Failed to configure {package.name}, exit message: {configure_resp}")
            return

        os.sync()
        if stage is not None:
            build_resp = package.build(stage)
            if isinstance(build_resp, Exception):
                print(f"Failed to build {package.name}[{stage.name}], exit code: {build_resp}")
                return

            os.sync()

            return configure_resp, build_resp
        else:
            build_resp = package.build(None)
            if isinstance(build_resp, Exception):
                print(f"Failed to build {package.name}, exit code: {build_resp}")
                return

            os.sync()

            return configure_resp, build_resp

    def build_deb(self, package: Package):
        package.copy_system()
        os.sync()

        package.make_deb({dep: self.lookup(dep).version for dep in package.pkg_deps()})
        os.sync()

    def build_package(self, package: Package | ToolPackage | SourcePackage, stage_name: str):
        self.make_dir(package)
        self.make_container(package)

        if isinstance(package, SourcePackage):
            return self.build_source(package)
        elif isinstance(package, ToolPackage):
            return self.build_tool(package, stage_name)
        elif isinstance(package, Package):
            values = self.build_system(package, stage_name)
            self.build_deb(package)

            return values
        raise Exception("Passed invalid object to build_package() !")

    def install_package(self, package: Package | ToolPackage | SourcePackage, stage_name: str):
        if isinstance(package, Package):
            if stage_name is None:
                self.make_dir(package)
                self.make_container(package)
                self.build_system(package, None)
                self.build_deb(package)
            else:
                self.make_dir(package)
                self.make_container(package)
                self.build_system(package, stage_name)
                self.build_deb(package)
            package.copy_system()
        elif isinstance(package, ToolPackage):
            if stage_name is None:
                self.make_dir(package)
                self.make_container(package)
                self.build_tool(package, None)
            else:
                self.make_dir(package)
                self.make_container(package)
                self.build_tool(package, stage_name)
            package.copy_tool()
        else:
            self.make_dir(package)
            self.make_container(package)
            self.build_source(package)

    def clean_package(self, package: Package | ToolPackage | SourcePackage):
        package.clean_dirs()

    def kill_build(self, package: Package | ToolPackage | SourcePackage):
        package.kill_build()