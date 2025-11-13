from apolo_apps_postgresql.outputs_processor import PostgresOutputsProcessor


async def test_postgres_outputs(setup_clients, mock_kubernetes_client, app_instance_id):
    processor = PostgresOutputsProcessor()
    res = await processor.generate_outputs(
        helm_values={"APOLO_PASSED_CONFIG": "{}"}, app_instance_id=app_instance_id
    )
    assert res["postgres_users"]["users"] == [
        {
            "__type__": "CrunchyPostgresUserCredentials",
            "dbname": "mydatabase",
            "user": "admin",
            "password": {
                "__type__": "ApoloSecret",
                "key": f"postgres-admin-password-{app_instance_id}",
            },
            "host": "db.example.com",
            "port": 5432,
            "pgbouncer_host": "pgbouncer.example.com",
            "pgbouncer_port": 6432,
            "pgbouncer_uri": {
                "__type__": "ApoloSecret",
                "key": f"postgres-admin-pgbouncer-uri-{app_instance_id}",
            },
            "postgres_uri": {
                "__type__": "ApoloSecret",
                "key": f"postgres-admin-connection-uri-{app_instance_id}",
            },
            "user_type": "user",
        },
        {
            "__type__": "CrunchyPostgresUserCredentials",
            "dbname": "otherdatabase",
            "user": "admin",
            "password": {
                "__type__": "ApoloSecret",
                "key": f"postgres-admin-password-{app_instance_id}",
            },
            "host": "db.example.com",
            "port": 5432,
            "pgbouncer_host": "pgbouncer.example.com",
            "pgbouncer_port": 6432,
            "pgbouncer_uri": {
                "__type__": "ApoloSecret",
                "key": f"postgres-admin-otherdatabase-pgbouncer-uri-{app_instance_id}",
            },
            "postgres_uri": {
                "__type__": "ApoloSecret",
                "key": f"postgres-admin-otherdatabase-connection-uri-{app_instance_id}",
            },
            "user_type": "user",
        },
    ]
    mock = mock_kubernetes_client["mock_custom_objects"]
    mock.list_namespaced_custom_object.assert_called_once_with(
        group="postgres-operator.crunchydata.com",
        version="v1beta1",
        namespace="default-namespace",
        plural="postgresclusters",
        label_selector=f"argocd.argoproj.io/instance={app_instance_id}",
    )
