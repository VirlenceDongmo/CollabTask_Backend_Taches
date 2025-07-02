import pika
import json
from django.conf import settings

class NotificationProducer:

    def __init__(self):
        self.connection_params = pika.ConnectionParameters(
            host=settings.RABBITMQ['HOST'],
            port=settings.RABBITMQ['PORT'],
            credentials=pika.PlainCredentials(
                settings.RABBITMQ['USER'],
                settings.RABBITMQ['PASSWORD']
            ),
            heartbeat=600,
            blocked_connection_timeout=300
        )

    def send_notification(self, notification_data):
        try:
            connection = pika.BlockingConnection(self.connection_params)
            channel = connection.channel()
            
            # Déclarez l'exchange avec le bon nom (celui que vous utilisez dans vos settings)
            channel.exchange_declare(
                exchange=settings.RABBITMQ['EXCHANGE'],
                exchange_type='direct',
                durable=True
            )
            
            # Déclarez la queue avec les bonnes propriétés
            channel.queue_declare(
                queue=settings.RABBITMQ['QUEUE'],
                durable=True,
                arguments={
                    'x-message-ttl': 86400000,  # TTL des messages (24h)
                    'x-max-length': 10000  # Nombre max de messages
                }
            )
            
            # Liez la queue à l'exchange
            channel.queue_bind(
                exchange=settings.RABBITMQ['EXCHANGE'],
                queue=settings.RABBITMQ['QUEUE'],
                routing_key=settings.RABBITMQ['ROUTING_KEY']
            )
            
            # Publiez le message
            channel.basic_publish(
                exchange=settings.RABBITMQ['EXCHANGE'],
                routing_key=settings.RABBITMQ['ROUTING_KEY'],
                body=json.dumps(notification_data),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Rend le message persistant
                    content_type='application/json'
                )
            )
            
            connection.close()
            print("✔ Notification envoyée à RabbitMQ")
            return True
        except Exception as e:
            print(f"❌ Erreur d'envoi à RabbitMQ: {str(e)}")
            return False
        
