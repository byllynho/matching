import logging
from kafka import KafkaProducer
from json import dumps

logger = logging.getLogger(__name__)

def init_kafka(kafka_server):
	''' Create a connection with the Kafka Server

		@returns SonadorImagingServer instance
	'''

	if not kafka_server:
		logger.error('Unable to initialize Kafka stream consumer due to an error. Check the value of the KAFKA_SERVER '
			+ 'environment variable.')
		raise ValueError('Invalid or malformed Kafka URL: %s' % kafka_server)
	
	#validate_url(kafka_server)
	producer = KafkaProducer(
			bootstrap_servers=kafka_server, 
			value_serializer=lambda x: dumps(x).encode('utf-8')
		)

	return producer