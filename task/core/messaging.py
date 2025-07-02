import pika
import json
from django.conf import settings

def publish_event(routing_key, event_data):
    try:
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=settings.RABBITMQ['HOST'],
                port=settings.RABBITMQ['PORT'],
                credentials=pika.PlainCredentials(
                    settings.RABBITMQ['USER'],
                    settings.RABBITMQ['PASSWORD']
                )
            )
        )
        channel = connection.channel()
        
        channel.exchange_declare(
            exchange=settings.RABBITMQ['EXCHANGE'],
            exchange_type='topic',
            durable=True
        )
        
        channel.basic_publish(
            exchange=settings.RABBITMQ['EXCHANGE'],
            routing_key=routing_key,
            body=json.dumps(event_data),
            properties=pika.BasicProperties(
                delivery_mode=2,  # Make message persistent
            )
        )
        
        connection.close()
        return True
    except Exception as e:
        print(f"Failed to publish event: {str(e)}")
        return False