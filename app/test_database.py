import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch, Mock
from app import database


class DatabaseTests(unittest.TestCase):
    def test_local_url_keeps_existing_behavior(self):
        with patch('psycopg.connect') as connect:
            database.connect('postgresql://localhost/test', autocommit=True)
            connect.assert_called_once_with('postgresql://localhost/test', autocommit=True)

    def test_lakebase_refreshes_credentials(self):
        client = Mock()
        client.postgres.generate_database_credential.side_effect = [
            SimpleNamespace(token='first'), SimpleNamespace(token='second')]
        env = {'PGHOST': 'example', 'PGUSER': 'app', 'PGDATABASE': 'db',
               'LAKEBASE_ENDPOINT': 'projects/test/branches/production/endpoints/primary'}
        with patch.dict(os.environ, env, clear=True), patch.object(database, '_token', None), \
             patch.object(database, '_refresh_at', 0), \
             patch.dict('sys.modules', {'databricks.sdk': SimpleNamespace(WorkspaceClient=lambda: client)}), \
             patch('psycopg.connect') as connect, \
             patch.object(database.time, 'monotonic', side_effect=[0, 10, 2800, 2800]):
            database.connect()
            database.connect()
            database.connect()
            self.assertEqual(client.postgres.generate_database_credential.call_count, 2)
            self.assertEqual([c.kwargs['password'] for c in connect.call_args_list],
                             ['first', 'first', 'second'])
            self.assertEqual(connect.call_args.kwargs['sslmode'], 'require')
