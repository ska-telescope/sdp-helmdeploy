import subprocess
from unittest.mock import patch

import ska_sdp_helmdeploy.helmdeploy as deploy
from ska_sdp_config import Config, Deployment


deploy.HELM = "/bin/helm"


@patch("subprocess.run")
def test_invoke(mock_run):
    deploy.invoke("ls")
    mock_run.assert_called_once()


@patch("subprocess.run")
def test_delete(mock_run):
    assert deploy.delete_helm("test", "0")
    mock_run.assert_called_once()
    mock_run.side_effect = subprocess.CalledProcessError(1, "test")
    assert not deploy.delete_helm("test", "0")
    assert mock_run.call_count == 2


@patch("subprocess.run")
def test_update(mock_run):
    deploy.update_helm()
    mock_run.assert_called_once()
    mock_run.side_effect = subprocess.CalledProcessError(1, "test")
    deploy.update_helm()
    assert mock_run.call_count == 2


def run_create(mock_run, config, byte_string=None):

    if byte_string is not None:
        e = subprocess.CalledProcessError(1, "test")
        e.stdout = byte_string
        mock_run.side_effect = e

    for txn in config.txn():
        deployment = txn.get_deployment("test")
        ok = deploy.create_helm(txn, "test", deployment)
    return ok


@patch("subprocess.run")
def test_create(mock_run):
    config = Config(backend="memory")

    for txn in config.txn():
        txn.create_deployment(
            Deployment("test", "helm", {"chart": "test", "values": {"test": "test"}})
        )
        assert deploy._get_deployment(txn, "test") is not None

    assert run_create(mock_run, config)
    mock_run.assert_called_once()
    assert not run_create(mock_run, config, byte_string=b"already exists")
    assert mock_run.call_count == 3
    assert not run_create(mock_run, config, byte_string=b"doesn't exist")
    assert mock_run.call_count == 4


@patch("ska_sdp_helmdeploy.helmdeploy.invoke")
def test_list(mock_invoke):
    deployments = ["test1", "test2", "test3"]
    # With prefix
    deploy.PREFIX = "test"
    releases = ["test-" + d for d in deployments]
    mock_invoke.return_value = "\n".join(releases)
    assert deploy.list_helm() == set(deployments)
    # No prefix (default)
    deploy.PREFIX = ""
    releases = deployments
    mock_invoke.return_value = "\n".join(releases)
    assert deploy.list_helm() == set(deployments)


def test_release_name():
    # With prefix
    deploy.PREFIX = "test"
    assert deploy.release_name("test") == "test-test"
    # No prefix (default)
    deploy.PREFIX = ""
    assert deploy.release_name("test") == "test"


@patch("subprocess.run")
def test_main(mock_run):
    deploy.main(backend="memory")
    assert mock_run.call_count > 0


@patch("signal.signal")
@patch("sys.exit")
def test_terminate(mock_exit, mock_signal):
    deploy.terminate(None, None)
