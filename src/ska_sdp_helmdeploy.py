"""
Helm deployment controller.

Installs/updates/uninstalls Helm releases depending on information in the SDP
configuration.
"""

# pylint: disable=C0103

import logging
import os
import signal
import shutil
import subprocess
import sys
import time
import re

import ska_sdp_config
from ska.logging import configure_logging
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
        cmd_line, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=HELM_TIMEOUT
    )
    # Log results
    log.debug("Code: {}".format(result.returncode))
    out = result.stdout.decode()
    for line in out.splitlines():
        log.debug("-> " + line)
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
    if PREFIX == "":
        release = dpl_id
    else:
        release = PREFIX + "-" + dpl_id
    return release


def delete_helm(txn, dpl_id):
    """
    Delete a Helm deployment.

    :param txn: config DB transaction
    :param dpl_id: deployment ID

    """
    # Try to delete
    try:
        release = release_name(dpl_id)
        helm_invoke("uninstall", release, "-n", NAMESPACE)
        return True
    except subprocess.CalledProcessError:
        return False  # Assume it was already gone


def create_helm(txn, dpl_id, deploy):
    """
    Create a new Helm deployment.

    :param txn: config DB transaction
    :param dpl_id: deployment ID
    :param deploy: the deployment

    """
    # Attempt install
    log.info("Creating deployment {}...".format(dpl_id))

    # Get chart name. If it does not contain '/', it is from the private
    # repository
    chart = deploy.args.get("chart")
    if "/" not in chart:
        chart = CHART_REPO_NAME + "/" + chart

    # Build command line
    release = release_name(dpl_id)
    cmd = ["install", release, chart, "-n", NAMESPACE]

    # Encode any parameters
    if "values" in deploy.args and isinstance(deploy.args, dict):
        val_str = ",".join(
            ["{}={}".format(k, v) for k, v in deploy.args["values"].items()]
        )
        cmd.extend(["--set", val_str])

    # Make the call
    try:
        helm_invoke(*cmd)
        return True

    except subprocess.CalledProcessError as e:

        # Already exists? Purge
        if "already exists" in e.stdout.decode():
            try:
                log.info("Purging deployment {}...".format(dpl_id))
                helm_invoke("uninstall", release, "-n", NAMESPACE)
                txn.loop()  # Force loop, this will cause a re-attempt
            except subprocess.CalledProcessError:
                log.error("Could not purge deployment {}!".format(dpl_id))
        else:
            log.error("Could not create deployment {}!".format(dpl_id))

    return False


def update_helm():
    """Refresh Helm chart repositories."""
    try:
        helm_invoke("repo", "update")
    except subprocess.CalledProcessError as e:
        log.error("Could not refresh chart repositories")


def list_helm():
    """
    List Helm deployments.

    :returns: set of deployment IDs

    """
    log.info("Helm release prefix: %s", PREFIX)
    # Query helm for chart releases
    releases = helm_invoke("list", "-q", "-n", NAMESPACE).splitlines()
    # Regular expression to match deployment IDs in release names
    if PREFIX == "":
        re_release = re.compile("^(?P<dpl_id>.+)$")
    else:
        re_release = re.compile("^{}-(?P<dpl_id>.+)$".format(PREFIX))
    # Filter releases for those matching deployments
    deploys = []
    for release in releases:
        match = re_release.match(release)
        if match is not None:
            dpl_id = match.group("dpl_id")
            deploys.append(dpl_id)
    return set(deploys)


def _get_deployment(txn, dpl_id):
    try:
        return txn.get_deployment(dpl_id)
    except ValueError as e:
        log.warning("Deployment {} failed validation: {}!".format(dpl_id, str(e)))
    return None


def main(backend="etcd3"):
    """
    Main loop of Helm controller.

    :param backend: for configuration database

    """
    # Instantiate configuration
    client = ska_sdp_config.Config(backend=backend)

    # TODO: Service lease + leader election

    # Load Helm repositories
    for name, url in CHART_REPO_LIST:
        helm_invoke("repo", "add", name, url)
    update_helm()

    next_chart_refresh = time.time() + CHART_REPO_REFRESH

    # Show
    log.info("Loading helm deployments...")

    # Query helm for active deployments
    deploys = list_helm()
    log.info("Found {} existing deployments.".format(len(deploys)))

    # Wait for something to happen
    for txn in client.txn():

        # Refresh charts?
        if time.time() > next_chart_refresh:
            next_chart_refresh = time.time() + CHART_REPO_REFRESH
            update_helm()

        # List deployments
        target_deploys = txn.list_deployments()

        # Check for deployments that we should delete
        for dpl_id in list(deploys):
            if dpl_id not in target_deploys:
                if delete_helm(txn, dpl_id):
                    deploys.remove(dpl_id)

        # Check for deployments we should add
        for dpl_id in target_deploys:
            if dpl_id not in deploys:

                # Get details
                deploy = _get_deployment(txn, dpl_id)

                # Right type?
                if deploy is None or deploy.type != "helm":
                    continue

                # Create it
                if create_helm(txn, dpl_id, deploy):
                    deploys.add(dpl_id)

        # Loop around, wait if we made no change
        txn.loop(wait=True, timeout=next_chart_refresh - time.time())


def terminate(signal, frame):
    """Terminate the program."""
    log.info("Asked to terminate")
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, terminate)
    main()
