"""
Workflow deployment monitor

Uses the Python Kubernetes API to monitor Workflows POD status and then transfers appropriate
data back to the Processing Block status in the Configuration Database
"""
import os
import sys
import logging
from kubernetes import client, config, watch

LOG = logging.getLogger(__name__)

# Configs can be set in Configuration class directly or using helper utility
file = os.getenv("KUBECONFIG")
if file is None:
    file = os.getenv("HOME") + "/.kube/config"
if os.path.isfile(file):
    config.load_kube_config()
elif os.getenv("KUBERNETES_SERVICE_HOST") is not None:
    config.load_incluster_config()

watch = watch.Watch()

NAMESPACE = os.getenv("SDP_HELM_NAMESPACE", "sdp")


def monitor_workflows(sdp_config):
    """
    Daemon Thread to monitor deployed Workflows and to copy appropriate data back to the
    Configuration Database
    """
    LOG.debug("Workflow monitoring started!")

    api_v1 = client.CoreV1Api()
    for event in watch.stream(api_v1.list_namespaced_pod, namespace=NAMESPACE):
        pod = event["object"]
        LOG.debug(
            "Workflow POD name %s in phase %s", pod.metadata.name, pod.status.phase
        )
        index = (pod.metadata.name).index("-workflow")
        pb_id = pod.metadata.name[5:index]

        for txn in sdp_config.txn():
            state = txn.get_processing_block_state(pb_id)
            try:
                logstr = api_v1.read_namespaced_pod_log(
                    pod.metadata.name, NAMESPACE, pretty="true"
                )
            except client.ApiException:
                exec_type, value, traceback = sys.exc_info()
                logstr = "kubernetes ApiIException\nreason={}\nstatus={}".format(
                    value.reason, value.status
                )
        status = {
            "k8s_status": pod.status.phase,
            "k8s_lastlog": logstr.split("\n")[-4:-1],
        }
        LOG.debug("POD status %s", status)
        if state is not None:
            state.update(status)
            for txn in sdp_config.txn():
                txn.update_processing_block_state(pb_id, state)
