import json
import re

import pika as mq
import pymysql
from classy_fastapi import Routable, get, post
from fastapi import HTTPException, BackgroundTasks, FastAPI
from starlette.middleware.cors import CORSMiddleware

from .models import BuildOrder
from .package import Package
from .registry import HPackageRegistry
from .source import SourcePackage
from .sql import HBuildLog
from .stage import Stage
from .tool import ToolPackage


def format_lookup_name(package: SourcePackage | ToolPackage | Package | Stage) -> str:
    if isinstance(package, SourcePackage):
        return f"source[{package.name}]"
    elif isinstance(package, Stage):
        return f"{package.package_name}[{package.name}]"
    else:
        return package.name

class HBuildServer(Routable):
    def __init__(self):
        super().__init__()
        self.registry = HPackageRegistry()

        self.credentials = mq.PlainCredentials('mq', 'mq')
        self.connection = mq.BlockingConnection(mq.ConnectionParameters('localhost',
                                                                   5672,
                                                                   credentials=self.credentials))
        self.channel = self.connection.channel()
        self.channel.queue_declare(queue = 'message_queue')

        self.sql_conn = pymysql.connect(host='localhost',
                                     user='root',
                                     password='sql',
                                     database='sql',
                                     cursorclass=pymysql.cursors.DictCursor)

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

    @get('/')
    def get_root(self) -> str:
        return "hello world"

    @get('/api/packages')
    def get_packages(self) -> dict[str, list[str]]:
        package_list = []
        for package in self.registry.packages + self.registry.tools + self.registry.sources:
            if isinstance(package, ToolPackage):
                package_list.append({
                    "name": package.name,
                    "type": "tool",
                    "stages": [
                        {
                            "stage_name": stage.name,
                            "name": f"{package.name}[{stage.name}]",
                            "package": package.name,
                        }
                        for stage in package.stages
                    ]
                })
            elif isinstance(package, Package) or isinstance(package, SourcePackage):
                package_list.append({
                    "name": package.name,
                    "type": "package" if isinstance(package, Package) else "source",
                })

        return {
            "packages": package_list
        }

    @get('/api/graph')
    def get_graph(self):
        self.channel.basic_publish(exchange='',
                                    routing_key='dispatch',
                                   body='graph')

        graph_json = None
        for _, _, raw_body in self.channel.consume('message_queue', auto_ack=True):
            body = raw_body.decode("utf-8")
            objects = body.split(":", maxsplit=1)

            operation = objects[0]
            if operation == "result_graph":
                self.channel.cancel()

                graph_json = objects[1]
                break

        return json.loads(graph_json)

    @get('/api/history')
    def get_history(self):
        history = HBuildLog.select_history(self.sql_conn)
        return {
            "past_jobs": [{
                "id": item["id"],
                "runner": item["runner"],
                "packages": item["packages"].split(","),
                "created_at": item["created_at"].strftime("%s"),
            } for item in history]
        }

    @get('/api/log/{name}')
    def get_log(self, name: str):
        if name not in self.registry.package_names + self.registry.tool_names + self.registry.source_names + self.registry.stage_names:
            raise HTTPException(status_code=404, detail=f"{name} is not a system, tool, or source package")

        package: Package | SourcePackage | ToolPackage = self.lookup(name)
        logs = HBuildLog.select_logs(self.sql_conn, format_lookup_name(package), None)

        return {
            "logs": logs
        }

    @get('/api/status/{name}')
    def get_status(self, name: str):
        if name not in self.registry.package_names + self.registry.tool_names + self.registry.source_names:
            raise HTTPException(status_code=404, detail=f"{name} is not a system, tool, or source package")

        package: Package | SourcePackage | ToolPackage = self.lookup(name)
        return {
            "return_code": package.last_return_status if package.last_return_status is not None else 0
        }

    @post('/api/build', status_code=202)
    def post_build(self, req: BuildOrder, background_tasks: BackgroundTasks) -> None:
        to_build = []
        for package in req.packages:
            if package.name in to_build:
                raise HTTPException(status_code=400, detail=f"Duplicate package {package.name} in build order")
            if package.name not in self.registry.package_names + self.registry.tool_names + self.registry.source_names + self.registry.stage_names:
                raise HTTPException(status_code=404, detail=f"Package {package.name} does not exist or is not available.")
            if package.stage:
                to_build.append(f"{package.name}[{package.stage}]")
            else:
                lookup_name = format_lookup_name(self.lookup(package.name))
                to_build.append(lookup_name)

        self.channel.basic_publish(exchange='',
                                   routing_key='dispatch',
                                   body=f"build:{','.join(to_build)}")

        #def execute_build():
        #    self.show_deps(to_build, req.build_to, dep_graph)
        #    self.process(req.build_to, install_order, dep_graph)
        #background_tasks.add_task(execute_build)

        return {
            "message": "Building packages"
        }

origins =  [
    'http://localhost:3000',
    'http://10.0.0.48:3000'
]

server = HBuildServer()
app = FastAPI()
app.include_router(server.router)
app.add_middleware(
    CORSMiddleware,
    allow_origins =origins,
    allow_credentials = True,
    allow_methods = ['*'],
    allow_headers = ['*']
)