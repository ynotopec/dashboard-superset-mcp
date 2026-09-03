#!/usr/bin/env python3
"""Main entry point for Superset K8s deployment."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Optional

import click
import yaml
from kubernetes import client, config
from kubernetes.client.rest import ApiException

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Defaults
DEFAULT_NAMESPACE = "superset"
DEFAULT_VERSION = "6.1.0"
DEFAULT_IMAGE = f"apache/superset:{DEFAULT_VERSION}"


class SupersetK8sDeployer:
    """Deploy Apache Superset on Kubernetes."""

    def __init__(
        self,
        namespace: str = DEFAULT_NAMESPACE,
        version: str = DEFAULT_VERSION,
        image: Optional[str] = None,
        replicas: int = 1,
        expose_nodeport: bool = False,
        enable_tls: bool = False,
    ):
        self.namespace = namespace
        self.version = version
        self.image = image or f"apache/superset:{version}"
        self.replicas = replicas
        self.expose_nodeport = expose_nodeport
        self.enable_tls = enable_tls

        # Load k8s config
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

        self.apps_v1 = client.AppsV1Api()
        self.core_v1 = client.CoreV1Api()
        self.networking_v1 = client.NetworkingV1Api()

    def deploy(self) -> dict:
        """Deploy full Superset stack."""
        logger.info("Deploying Superset %s to namespace %s", self.version, self.namespace)

        # Create namespace if not exists
        self._create_namespace()

        # Deploy PostgreSQL
        self._deploy_postgres()

        # Deploy Redis
        self._deploy_redis()

        # Deploy Web Server
        self._deploy_webserver()

        # Deploy Worker
        self._deploy_worker()

        # Deploy MCP Server
        self._deploy_mcp()

        # Create services
        self._create_services()

        # Wait for pods
        self._wait_for_deploy()

        return self.get_status()

    def _create_namespace(self) -> None:
        """Create namespace if it doesn't exist."""
        try:
            self.core_v1.read_namespace(self.namespace)
            logger.info("Namespace %s already exists", self.namespace)
        except ApiException as exc:
            if exc.status == 404:
                body = client.V1Namespace(metadata=client.V1ObjectMeta(name=self.namespace))
                self.core_v1.create_namespace(body)
                logger.info("Created namespace %s", self.namespace)

    def _deploy_postgres(self) -> None:
        """Deploy PostgreSQL StatefulSet."""
        logger.info("Deploying PostgreSQL StatefulSet...")

        # Create secret for DB password
        import secrets
        db_password = secrets.token_hex(16)

        secret = client.V1Secret(
            metadata=client.V1ObjectMeta(name="superset-postgres-secret"),
            string_data={"postgres-password": db_password},
        )
        self.core_v1.create_namespaced_secret(self.namespace, secret)

        # Create PVC
        pvc = client.V1PersistentVolumeClaim(
            metadata=client.V1ObjectMeta(name="superset-postgres-data"),
            spec=client.V1PersistentVolumeClaimSpec(
                access_modes=["ReadWriteOnce"],
                resources=client.V1ResourceRequirements(
                    requests={"storage": "10Gi"},
                ),
            ),
        )
        self.core_v1.create_namespaced_persistent_volume_claim(self.namespace, pvc)

        # Deploy StatefulSet
        env = [
            client.V1EnvVar(name="POSTGRES_USER", value="superset"),
            client.V1EnvVar(name="POSTGRES_PASSWORD", value=db_password),
            client.V1EnvVar(name="POSTGRES_DB", value="superset"),
            client.V1EnvVar(name="PGDATA", value="/var/lib/postgresql/data/pgdata"),
        ]

        container = client.V1Container(
            name="postgres",
            image="postgres:15",
            ports=[client.V1ContainerPort(container_port=5432)],
            env=env,
            volume_mounts=[
                client.V1VolumeMount(name="data", mount_path="/var/lib/postgresql/data"),
            ],
            resources=client.V1ResourceRequirements(
                requests={"cpu": "500m", "memory": "512Mi"},
                limits={"cpu": "1000m", "memory": "1Gi"},
            ),
        )

        statefulset = client.V1StatefulSet(
            api_version="apps/v1",
            kind="StatefulSet",
            metadata=client.V1ObjectMeta(name="superset-postgres"),
            spec=client.V1StatefulSetSpec(
                replicas=1,
                selector=client.V1LabelSelector(
                    match_labels={"app": "superset-postgres"}
                ),
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(labels={"app": "superset-postgres"}),
                    spec=client.V1PodSpec(
                        containers=[container],
                        volumes=[
                            client.V1Volume(
                                name="data",
                                persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                                    claim_name="superset-postgres-data"
                                ),
                            )
                        ],
                    ),
                ),
            ),
        )

        self.apps_v1.create_namespaced_stateful_set(self.namespace, statefulset)
        logger.info("PostgreSQL StatefulSet created")

    def _deploy_redis(self) -> None:
        """Deploy Redis Deployment."""
        logger.info("Deploying Redis Deployment...")

        container = client.V1Container(
            name="redis",
            image="redis:7-alpine",
            ports=[client.V1ContainerPort(container_port=6379)],
            resources=client.V1ResourceRequirements(
                requests={"cpu": "250m", "memory": "256Mi"},
                limits={"cpu": "500m", "memory": "512Mi"},
            ),
        )

        deployment = client.V1Deployment(
            api_version="apps/v1",
            kind="Deployment",
            metadata=client.V1ObjectMeta(name="superset-redis"),
            spec=client.V1DeploymentSpec(
                replicas=1,
                selector=client.V1LabelSelector(
                    match_labels={"app": "superset-redis"}
                ),
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(labels={"app": "superset-redis"}),
                    spec=client.V1PodSpec(containers=[container]),
                ),
            ),
        )

        self.apps_v1.create_namespaced_deployment(self.namespace, deployment)
        logger.info("Redis Deployment created")

    def _deploy_webserver(self) -> None:
        """Deploy Superset Web Server."""
        logger.info("Deploying Superset Web Server...")

        env = [
            client.V1EnvVar(name="SUPERSET_CONFIG_PATH", value="/app/superset_config.py"),
            client.V1EnvVar(name="DATABASE_HOST", value="superset-postgres"),
            client.V1EnvVar(name="DATABASE_PORT", value="5432"),
            client.V1EnvVar(name="DATABASE_USER", value="superset"),
            client.V1EnvVar(name="DATABASE_NAME", value="superset"),
            client.V1EnvVar(name="SECRET_KEY", value="CHANGE-ME-IN-PRODUCTION"),
            client.V1EnvVar(name="MCP_AUTH_ENABLED", value="False"),
            client.V1EnvVar(name="MCP_DEV_USERNAME", value="admin"),
            client.V1EnvVar(name="CACHE_REDIS_HOST", value="superset-redis"),
            client.V1EnvVar(name="CACHE_REDIS_PORT", value="6379"),
            client.V1EnvVar(name="CACHE_REDIS_DB", value="0"),
            client.V1EnvVar(name="BROKER_REDIS_HOST", value="superset-redis"),
            client.V1EnvVar(name="BROKER_REDIS_PORT", value="6379"),
            client.V1EnvVar(name="BROKER_REDIS_DB", value="1"),
            client.V1EnvVar(name="RESULT_BACKEND_REDIS_HOST", value="superset-redis"),
            client.V1EnvVar(name="RESULT_BACKEND_REDIS_PORT", value="6379"),
            client.V1EnvVar(name="RESULT_BACKEND_REDIS_DB", value="2"),
        ]

        container = client.V1Container(
            name="superset-webserver",
            image=self.image,
            ports=[client.V1ContainerPort(container_port=8088)],
            env=env,
            readiness_probe=client.V1Probe(
                http_get=client.V1HTTPGetAction(path="/health", port=8088),
                initial_delay_seconds=30,
                period_seconds=10,
            ),
            liveness_probe=client.V1Probe(
                http_get=client.V1HTTPGetAction(path="/health", port=8088),
                initial_delay_seconds=60,
                period_seconds=30,
            ),
            resources=client.V1ResourceRequirements(
                requests={"cpu": "500m", "memory": "512Mi"},
                limits={"cpu": "1000m", "memory": "1Gi"},
            ),
        )

        deployment = client.V1Deployment(
            api_version="apps/v1",
            kind="Deployment",
            metadata=client.V1ObjectMeta(name="superset-webserver"),
            spec=client.V1DeploymentSpec(
                replicas=self.replicas,
                selector=client.V1LabelSelector(
                    match_labels={"app": "superset-webserver"}
                ),
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(labels={"app": "superset-webserver"}),
                    spec=client.V1PodSpec(containers=[container]),
                ),
            ),
        )

        self.apps_v1.create_namespaced_deployment(self.namespace, deployment)
        logger.info("Web Server Deployment created")

    def _deploy_worker(self) -> None:
        """Deploy Superset Worker (Celery)."""
        logger.info("Deploying Superset Worker...")

        env = [
            client.V1EnvVar(name="DATABASE_HOST", value="superset-postgres"),
            client.V1EnvVar(name="DATABASE_PORT", value="5432"),
            client.V1EnvVar(name="DATABASE_USER", value="superset"),
            client.V1EnvVar(name="DATABASE_NAME", value="superset"),
            client.V1EnvVar(name="SECRET_KEY", value="CHANGE-ME-IN-PRODUCTION"),
            client.V1EnvVar(name="CACHE_REDIS_HOST", value="superset-redis"),
            client.V1EnvVar(name="CACHE_REDIS_PORT", value="6379"),
            client.V1EnvVar(name="CACHE_REDIS_DB", value="0"),
            client.V1EnvVar(name="BROKER_REDIS_HOST", value="superset-redis"),
            client.V1EnvVar(name="BROKER_REDIS_PORT", value="6379"),
            client.V1EnvVar(name="BROKER_REDIS_DB", value="1"),
            client.V1EnvVar(name="RESULT_BACKEND_REDIS_HOST", value="superset-redis"),
            client.V1EnvVar(name="RESULT_BACKEND_REDIS_PORT", value="6379"),
            client.V1EnvVar(name="RESULT_BACKEND_REDIS_DB", value="2"),
        ]

        container = client.V1Container(
            name="superset-worker",
            image=self.image,
            env=env,
            command=["superset", "celery", "worker"],
            resources=client.V1ResourceRequirements(
                requests={"cpu": "500m", "memory": "512Mi"},
                limits={"cpu": "1000m", "memory": "1Gi"},
            ),
        )

        deployment = client.V1Deployment(
            api_version="apps/v1",
            kind="Deployment",
            metadata=client.V1ObjectMeta(name="superset-worker"),
            spec=client.V1DeploymentSpec(
                replicas=1,
                selector=client.V1LabelSelector(
                    match_labels={"app": "superset-worker"}
                ),
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(labels={"app": "superset-worker"}),
                    spec=client.V1PodSpec(containers=[container]),
                ),
            ),
        )

        self.apps_v1.create_namespaced_deployment(self.namespace, deployment)
        logger.info("Worker Deployment created")

    def _deploy_mcp(self) -> None:
        """Deploy MCP Server as a separate deployment."""
        logger.info("Deploying MCP Server...")

        env = [
            client.V1EnvVar(name="DATABASE_HOST", value="superset-postgres"),
            client.V1EnvVar(name="DATABASE_PORT", value="5432"),
            client.V1EnvVar(name="DATABASE_USER", value="superset"),
            client.V1EnvVar(name="DATABASE_NAME", value="superset"),
            client.V1EnvVar(name="SECRET_KEY", value="CHANGE-ME-IN-PRODUCTION"),
            client.V1EnvVar(name="CACHE_REDIS_HOST", value="superset-redis"),
            client.V1EnvVar(name="CACHE_REDIS_PORT", value="6379"),
            client.V1EnvVar(name="CACHE_REDIS_DB", value="0"),
            client.V1EnvVar(name="BROKER_REDIS_HOST", value="superset-redis"),
            client.V1EnvVar(name="BROKER_REDIS_PORT", value="6379"),
            client.V1EnvVar(name="BROKER_REDIS_DB", value="1"),
            client.V1EnvVar(name="RESULT_BACKEND_REDIS_HOST", value="superset-redis"),
            client.V1EnvVar(name="RESULT_BACKEND_REDIS_PORT", value="6379"),
            client.V1EnvVar(name="RESULT_BACKEND_REDIS_DB", value="2"),
        ]

        container = client.V1Container(
            name="superset-mcp",
            image=self.image,
            ports=[client.V1ContainerPort(container_port=5008)],
            env=env,
            command=["superset", "mcp", "run", "--host", "0.0.0.0", "--port", "5008"],
            resources=client.V1ResourceRequirements(
                requests={"cpu": "250m", "memory": "256Mi"},
                limits={"cpu": "500m", "memory": "512Mi"},
            ),
            readiness_probe=client.V1Probe(
                http_get=client.V1HTTPGetAction(path="/mcp", port=5008),
                initial_delay_seconds=30,
                period_seconds=10,
            ),
        )

        deployment = client.V1Deployment(
            api_version="apps/v1",
            kind="Deployment",
            metadata=client.V1ObjectMeta(name="superset-mcp"),
            spec=client.V1DeploymentSpec(
                replicas=1,
                selector=client.V1LabelSelector(
                    match_labels={"app": "superset-mcp"}
                ),
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(labels={"app": "superset-mcp"}),
                    spec=client.V1PodSpec(containers=[container]),
                ),
            ),
        )

        self.apps_v1.create_namespaced_deployment(self.namespace, deployment)
        logger.info("MCP Server Deployment created")

    def _create_services(self) -> None:
        """Create Kubernetes services."""
        services = [
            {
                "name": "superset-postgres",
                "port": 5432,
                "target_port": 5432,
                "app": "superset-postgres",
            },
            {
                "name": "superset-redis",
                "port": 6379,
                "target_port": 6379,
                "app": "superset-redis",
            },
            {
                "name": "superset-webserver",
                "port": 8088,
                "target_port": 8088,
                "app": "superset-webserver",
            },
            {
                "name": "superset-worker",
                "port": 8080,  # Internal only
                "target_port": 8080,
                "app": "superset-worker",
            },
            {
                "name": "superset-mcp",
                "port": 5008,
                "target_port": 5008,
                "app": "superset-mcp",
            },
        ]

        for svc_def in services:
            # Check if service already exists
            try:
                self.core_v1.read_namespaced_service(svc_def["name"], self.namespace)
                logger.info("Service %s already exists", svc_def["name"])
                continue
            except ApiException as exc:
                if exc.status != 404:
                    raise

            # Create service
            if self.expose_nodeport and svc_def["name"] == "superset-webserver":
                service_type = "NodePort"
            else:
                service_type = "ClusterIP"

            port = client.V1ServicePort(
                port=svc_def["port"],
                target_port=svc_def["target_port"],
                node_port=svc_def["port"] if service_type == "NodePort" else None,
            )

            service = client.V1Service(
                api_version="v1",
                kind="Service",
                metadata=client.V1ObjectMeta(name=svc_def["name"]),
                spec=client.V1ServiceSpec(
                    selector={"app": svc_def["app"]},
                    ports=[port],
                    type=service_type,
                ),
            )

            self.core_v1.create_namespaced_service(self.namespace, service)
            logger.info("Service %s created", svc_def["name"])

    def _wait_for_deploy(self) -> None:
        """Wait for all pods to be running."""
        logger.info("Waiting for pods to be running...")

        timeout = 300  # 5 minutes
        elapsed = 0

        while elapsed < timeout:
            try:
                pods = self.core_v1.list_namespaced_pod(
                    self.namespace,
                    label_selector="app in (superset-webserver,superset-worker,superset-postgres,superset-redis,superset-mcp)",
                )

                all_running = True
                for pod in pods.items:
                    phase = pod.status.phase
                    if phase != "Running":
                        all_running = False
                        logger.info(
                            "  Pod %s: %s", pod.metadata.name, phase
                        )
                        break

                if all_running:
                    logger.info("All pods are running!")
                    return

            except ApiException:
                pass

            import time
            time.sleep(10)
            elapsed += 10
            logger.info("  Waiting... (%ds/%ds)", elapsed, timeout)

        raise TimeoutError(
            f"Timeout waiting for pods to be running after {timeout}s"
        )

    def get_status(self) -> dict:
        """Get deployment status."""
        pods = self.core_v1.list_namespaced_pod(self.namespace)
        status = {"pods": [], "services": []}

        for pod in pods.items:
            status["pods"].append({
                "name": pod.metadata.name,
                "phase": pod.status.phase,
                "ready": f"{pod.status.container_statuses[0].ready if pod.status.container_statuses else False}",
            })

        services = self.core_v1.list_namespaced_service(self.namespace)
        for svc in services.items:
            status["services"].append({
                "name": svc.metadata.name,
                "type": svc.spec.type,
                "ports": [f"{p.port}:{p.target_port}" for p in svc.spec.ports],
            })

        return status


@click.group()
def cli():
    """CLI for deploying Superset on Kubernetes."""
    pass


@cli.command()
@click.option("--namespace", default=DEFAULT_NAMESPACE, help="Kubernetes namespace")
@click.option("--version", default=DEFAULT_VERSION, help="Superset version")
@click.option("--replicas", default=1, help="Number of web server replicas")
@click.option("--expose-nodeport", is_flag=True, help="Expose via NodePort")
@click.option("--enable-tls", is_flag=True, help="Enable TLS")
def deploy(namespace, version, replicas, expose_nodeport, enable_tls):
    """Deploy Superset on Kubernetes."""
    deployer = SupersetK8sDeployer(
        namespace=namespace,
        version=version,
        replicas=replicas,
        expose_nodeport=expose_nodeport,
        enable_tls=enable_tls,
    )

    try:
        result = deployer.deploy()
        print(json.dumps(result, indent=2))
    except Exception as exc:
        logger.error("Deployment failed: %s", exc)
        sys.exit(1)


@cli.command()
@click.option("--namespace", default=DEFAULT_NAMESPACE, help="Kubernetes namespace")
def status(namespace):
    """Show deployment status."""
    try:
        config.load_kube_config()
    except config.ConfigException:
        config.load_incluster_config()

    core_v1 = client.CoreV1Api()

    pods = core_v1.list_namespaced_pod(namespace)
    print(f"Pods in {namespace}:")
    for pod in pods.items:
        print(f"  {pod.metadata.name}: {pod.status.phase}")

    services = core_v1.list_namespaced_service(namespace)
    print(f"\nServices in {namespace}:")
    for svc in services.items:
        print(f"  {svc.metadata.name}: {svc.spec.type}")


@cli.command()
@click.option("--namespace", default=DEFAULT_NAMESPACE, help="Kubernetes namespace")
@click.option("--yes", is_flag=True, help="Skip confirmation")
def destroy(namespace, yes):
    """Destroy Superset deployment."""
    if not yes:
        confirm = input(f"Destroy Superset in namespace {namespace}? (y/N): ")
        if confirm.lower() != "y":
            print("Cancelled")
            return

    try:
        config.load_kube_config()
    except config.ConfigException:
        config.load_incluster_config()

    apps_v1 = client.AppsV1Api()
    core_v1 = client.CoreV1Api()

    # Delete deployments
    for name in ["superset-webserver", "superset-worker", "superset-redis", "superset-mcp"]:
        try:
            apps_v1.delete_namespaced_deployment(name, namespace)
            print(f"Deleted deployment {name}")
        except ApiException as exc:
            if exc.status == 404:
                print(f"Deployment {name} not found")

    # Delete StatefulSet
    try:
        apps_v1.delete_namespaced_stateful_set("superset-postgres", namespace)
        print("Deleted StatefulSet superset-postgres")
    except ApiException as exc:
        if exc.status != 404:
            raise

    print("Deployment destroyed")


if __name__ == "__main__":
    cli()
