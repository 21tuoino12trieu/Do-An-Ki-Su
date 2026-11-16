import json
from unittest import TestCase
from unittest.mock import patch, MagicMock

from beegenerate.loggings.handlers.kafka import KafkaLoggingHandler


class TestKafkaLoggingHandler(TestCase):

    @patch('beegen.logs.handlers.kafka.KafkaProducer')
    @patch('beegen.logs.handlers.kafka.socket.gethostbyname')
    @patch('beegen.logs.handlers.kafka.socket.gethostname')
    def test_init_success_wit_sasl_plaintext(self, mock_gethostname, mock_gethostbyname, mock_kafkaproducer):
        # # Arrange
        mock_gethostname.return_value = 'localhost'
        mock_gethostbyname.return_value = '127.0.0.1'
        mock_value_serializer = MagicMock()

        handler = KafkaLoggingHandler(
            hosts_list=['10.1.54.24:9093', '10.1.54.25:9093', '10.1.54.26:9093', '10.1.54.27:9093', '10.1.54.28:9093', '10.1.54.29:9093'],
            topic='log_beegen_core',
            security_protocol='SASL_PLAINTEXT',
            ssl_cafile=None,
            kafka_producer_args={
                'client_id': 'beegen-core',
                'sasl_mechanism': 'SCRAM-SHA-512',
                'sasl_plain_username': 'user24',
                'sasl_plain_password': 'user24',
            }
        )

        #Assert
        self.assertTrue(handler.enabled)
        self.assertEqual(handler.producer, mock_kafkaproducer.return_value)
        self.assertEqual(handler.additional_fields, {'host': mock_gethostname.return_value, 'host_ip': mock_gethostbyname.return_value})
        self.assertEqual(handler.kafka_topic_name, "log_beegen_core")

        called_kwargs = mock_kafkaproducer.call_args.kwargs
        called_kwargs["value_serializer"] = mock_value_serializer

        mock_kafkaproducer.assert_called_once_with(
            bootstrap_servers=['10.1.54.24:9093', '10.1.54.25:9093', '10.1.54.26:9093', '10.1.54.27:9093', '10.1.54.28:9093', '10.1.54.29:9093'],
            security_protocol='SASL_PLAINTEXT',
            ssl_cafile=None,
            value_serializer=mock_value_serializer,
            client_id='beegen-core',
            sasl_mechanism='SCRAM-SHA-512',
            sasl_plain_username='user24',
            sasl_plain_password='user24'
        )

    def test_prepare_record_dict(self):
        self.fail()

    def test_emit(self):
        self.fail()

    def test_append_to_buffer(self):
        self.fail()

    def test_flush(self):
        self.fail()

    def test_schedule_flush(self):
        self.fail()

    def test_mp_log_handler(self):
        self.fail()

    def test_at_exit(self):
        self.fail()

    def test_unhandled_exception(self):
        self.fail()

    def test_close(self):
        self.fail()
