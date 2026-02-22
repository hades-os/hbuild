from kombu import Connection, Exchange, Queue
from kombu.mixins import ConsumerMixin
class RobustWorker(ConsumerMixin):
    def __init__(self, connection, queues, on_message_callback=None):
        self.connection = connection
        self.queues = queues
        self.on_message_callback = on_message_callback

    def get_consumers(self, Consumer, channel):
        return [Consumer(queues=self.queues,
                         callbacks=[self.on_message])]

    def on_message(self, body, message):
        if self.on_message_callback:
            self.on_message_callback(body, message)
        message.ack()