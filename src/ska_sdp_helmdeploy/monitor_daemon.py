"""
Workflow deployment monitor

Uses the Python Kubernetes API to monitor Workflows POD status and then transfers appropriate
data back to the Processing Block status in the Configuration Database
"""
import os
import logging
from kubernetes import client, config, watch
import ska_sdp_config
from ska.logging import configure_logging

LOG_LEVEL = os.getenv("SDP_LOG_LEVEL", "DEBUG")

LOG = logging.getLogger(__name__)

# Configs can be set in Configuration class directly or using helper utility
#config.load_kube_config()
config.load_incluster_config()
watch = watch.Watch()

# Connect to config DB
LOG.info("Connecting to config DB")
sdp_config = ska_sdp_config.Config(backend=None)
NAMESPACE = os.getenv("SDP_HELM_NAMESPACE", "sdp")

def monitor_workflows():
    """
    Daemon Thread to monitor deployed Workflows and to copy appropriate data back to the
    Configuration Database
    """

    v1 = client.CoreV1Api()
    for event in watch.stream(v1.list_namespaced_pod, namespace=NAMESPACE):
        pod = event['object']
        LOG.info("Workflow POD name %s in phase %s", pod.metadata.name, pod.status.phase)
        index = (pod.metadata.name).index('-workflow')
        pb_id = pod.metadata.name[5:index]

        for txn in sdp_config.txn():
            state = txn.get_processing_block_state(pb_id)
      
        try:
           logstr = v1.read_namespaced_pod_log(pod.metadata.name, "sdp", pretty='true')
        except Exception:
           pass 
        status= {"k8s_status": pod.status.phase,"k8s_lastlog":logstr.split("\n")[-4:-1]}
        LOG.info("POD status %s, status)
        if state != None:
           state.update(status)
           for txn in sdp_config.txn():
              txn.update_processing_block_state(pb_id, state)

