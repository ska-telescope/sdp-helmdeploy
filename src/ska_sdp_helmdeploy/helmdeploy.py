"""
Helm deployment controller.

Installs/updates/uninstalls Helm releases depending on information in the SDP
configuration.
"""

import logging
import os
import signal
import shutil
import subprocess
import sys
import tempfile
import time
import threading
import yaml

import ska_sdp_config
from ska_ser_logging import configure_logging
from dotenv import load_dotenv

load_dotenv()

# Load environment
HELM = shutil.which(os.getenv("SDP_HELM", "helm"))
HELM_TIMEOUT = int(os.getenv("SDP_HELM_TIMEOUT", "300"))
NAMESPACE = os.getenv("SDP_HELM_NAMESPACE", "sdp")
PREFIX = os.getenv("SDP_HELM_PREFIX", "")
CHART_REPO_URL = os.getenv(
    "SDP_CHART_REPO_URL",
    "https://gitlab.com/ska-telescope/sdp/ska-sdp-helmdeploy-charts/-/raw/master/chart-repo/",
)
CHART_REPO_REFRESH = int(os.getenv("SDP_CHART_REPO_REFRESH", "300"))
LOG_LEVEL = os.getenv("SDP_LOG_LEVEL", "DEBUG")

# Name to use for the Helm deployer's own repository
CHART_REPO_NAME = "helmdeploy"
# Chart repositories to use, as a list of (name, url) pairs
CHART_REPO_LIST = [
    (CHART_REPO_NAME, CHART_REPO_URL),
    ("dask", "https://helm.dask.org/"),
]

# Initialise logger.
configure_logging(level=LOG_LEVEL)
log = logging.getLogger(__name__)


def invoke(*cmd_line):
    """
    Invoke a command with the given command line.

    :returns: output of the command
    :raises: ``subprocess.CalledProcessError`` if command returns an error status

    """
    # Perform call
    log.debug(" ".join(["$"] + list(cmd_line)))
    result = subprocess.run(
        cmd_line,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=HELM_TIMEOUT,
        check=True,
    )
    # Log results
    log.debug("Code: %s", result.returncode)
    out = result.stdout.decode()
    for line in out.splitlines():
        log.debug("-> %s", line)
    result.check_returncode()
    return out


def helm_invoke(*args):
    """
    Invoke Helm with the given command-line arguments.

    :returns: output of the command
    :raises: ``subprocess.CalledProcessError`` if command returns an error status

    """
    return invoke(*([HELM] + list(args)))


def release_name(dpl_id):
    """
    Get Helm release name from deployment ID.

    :param dpl_id: deployment ID
    :returns: release name

    """
    if PREFIX:
        release = PREFIX + "-" + dpl_id
    else:
        release = dpl_id
    return release


def delete_helm(dpl_id):
    """
    Delete a Helm deployment.

    :param dpl_id: deployment ID

    """
    log.info("Deleting deployment %s...", dpl_id)

    # Try to delete
    try:
        release = release_name(dpl_id)
        helm_invoke("uninstall", release, "-n", NAMESPACE)
        return True
    except subprocess.CalledProcessError:
        return False  # Assume it was already gone


def create_helm(dpl_id, deploy):
    """
    Create a new Helm deployment.

    :param dpl_id: deployment ID
    :param deploy: the deployment

    """
    log.info("Creating deployment %s...", dpl_id)

    # Get chart name. If it does not contain '/', it is from the private
    # repository
    chart = deploy.args.get("chart")
    if "/" not in chart:
        chart = CHART_REPO_NAME + "/" + chart
    log.debug("Chart: %s", chart)

    # Build command line
    release = release_name(dpl_id)
    cmd = ["install", release, chart, "-n", NAMESPACE]

    # Write any values to a temporary file
    if "values" in deploy.args:
        values = yaml.dump(deploy.args["values"])
        log.debug("Values:")
        for line in values.splitlines():
            log.debug("-> %s", line)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as file:
            file.write(values)
        filename = file.name
        cmd.extend(["-f", filename])
    else:
        filename = None

    # Try to create
    try:
        helm_invoke(*cmd)
        success = True
    except subprocess.CalledProcessError:
        log.error("Could not create deployment %s!", dpl_id)
        success = False

    # Delete values file, if used
    if filename:
        os.unlink(filename)

    return success


def update_helm():
    """Refresh Helm chart repositories."""
    try:
        helm_invoke("repo", "update")
    except subprocess.CalledProcessError:
        log.error("Could not refresh chart repositories")


def list_helm():
    """
    List Helm deployments.

    :returns: list of deployment IDs

    """
    # Query helm for chart releases
    releases = helm_invoke("list", "-q", "-n", NAMESPACE).splitlines()
    if PREFIX:
        # Filter releases for those matching deployments
        deploys = [
            release[len(PREFIX) + 1 :]
            for release in releases
            if release.startswith(PREFIX + "-")
        ]
    else:
        deploys = releases
    return deploys


def _get_deployment(txn, dpl_id):
    try:
        return txn.get_deployment(dpl_id)
    except ValueError as error:
        log.warning("Deployment %s failed validation: %s!", dpl_id, str(error))
    return None


def main_loop(backend=None):
    """
    Main loop of Helm controller.

    :param backend: for configuration database

    """
    # Instantiate configuration
    client = ska_sdp_config.Config(backend=backend)

    # Configure Helm repositories
    for name, url in CHART_REPO_LIST:
        helm_invoke("repo", "add", name, url)

    # Get charts
    update_helm()
    next_chart_refresh = time.time() + CHART_REPO_REFRESH

    # Start thread to monitor Kubernetes events in the Helm Namespace
    f = os.getenv("KUBECONFIG")
    if f is None:
        f = os.getenv("HOME") + "/.kube/config"
    for file in [f, "/var/run/secrets/kubernetes.io"]:
        if os.path.isfile(file):
            monitor_thread = threading.Thread(target=monitor_workflows, daemon=True)
            monitor_thread.start()

    # Wait for something to happen
    for watcher in client.watcher(timeout=CHART_REPO_REFRESH):

        # Refresh charts?
        if time.time() > next_chart_refresh:
            update_helm()
            next_chart_refresh = time.time() + CHART_REPO_REFRESH

        # List deployments
        deploys = list_helm()
        for txn in watcher.txn():
            target_deploys = txn.list_deployments()

        # Check for deployments we should delete
        for dpl_id in deploys:
            if dpl_id not in target_deploys:
                # Delete it
                delete_helm(dpl_id)

        # Check for deployments we should add
        for dpl_id in target_deploys:
            if dpl_id not in deploys:
                # Get details
                for txn in watcher.txn():
                    deploy = _get_deployment(txn, dpl_id)
                # If vanished or wrong type, ignore
                if deploy is None or deploy.type != "helm":
                    continue
                # Create it
                create_helm(dpl_id, deploy)


def terminate(_signame, _frame):
    """Terminate the program."""
    log.info("Asked to terminate")
    sys.exit(0)


def main(backend=None):
    """Main."""
    signal.signal(signal.SIGTERM, terminate)
    main_loop(backend=backend)


# Replaced __main__.py with this construct to simplify testing.
if __name__ == "__main__":
    main()
