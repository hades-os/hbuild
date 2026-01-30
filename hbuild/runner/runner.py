from hbuild.registry import HPackageRegistry

import pika as mq

class HBuildRunner():
    def __init__(self):
        self.registry = HPackageRegistry()

        self.credentials = mq.PlainCredentials('mq', 'mq')
        self.connection = mq.BlockingConnection(mq.ConnectionParameters('localhost',
                                                                   5672,
                                                                   credentials=self.credentials))
        self.channel = self.connection.channel()
        self.channel.queue_declare(queue = 'runners')
        self.channel.basic_consume(queue = 'runners', on_message_callback = self.consume, auto_ack=True)

    def run_server(self):
        self.channel.start_consuming()

    def consume(self, channel, method, properties, raw_body):
        body = raw_body.decode("utf-8")
        objects = body.split(":")
        operation = objects[0]
        if operation == "execute":
            requested_packages = objects[1].split(",")
