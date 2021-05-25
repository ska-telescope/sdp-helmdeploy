import subprocess
from unittest.mock import patch

from ska_sdp_config import Config, Deployment
from ska_sdp_helmdeploy import helmdeploy

helmdeploy.HELM = "/bin/helm"


@patch("subprocess.run")
def test_invoke(mock_run):
    helmdeploy.invoke("ls")
    mock_run.assert_called_once()


@patch("subprocess.run")
def test_delete(mock_run):
    assert helmdeploy.delete_helm("test")
    mock_run.assert_called_once()
    mock_run.side_effect = subprocess.CalledProcessError(1, "test")
    assert not helmdeploy.delete_helm("test")
    assert mock_run.call_count == 2


@patch("subprocess.run")
def test_update(mock_run):
    helmdeploy.update_helm()
    mock_run.assert_called_once()
    mock_run.side_effect = subprocess.CalledProcessError(1, "test")
    helmdeploy.update_helm()
    assert mock_run.call_count == 2


def run_create(mock_run, config, byte_string=None):

    if byte_string is not None:
        e = subprocess.CalledProcessError(1, "test")
        e.stdout = byte_string
        mock_run.side_effect = e

    for txn in config.txn():
        deployment = txn.get_deployment("test")
    ok = helmdeploy.create_helm("test", deployment)

    return ok


@patch("subprocess.run")
def test_create(mock_run):
    config = Config(backend="memory")

    for txn in config.txn():
        txn.create_deployment(
            Deployment("test", "helm", {"chart": "test", "values": {"test": "test"}})
        )
    for txn in config.txn():
        assert helmdeploy._get_deployment(txn, "test") is not None

    assert run_create(mock_run, config)
    mock_run.assert_called_once()
    assert not run_create(mock_run, config, byte_string=b"already exists")
    assert mock_run.call_count == 2
    assert not run_create(mock_run, config, byte_string=b"doesn't exist")
    assert mock_run.call_count == 3


@patch("ska_sdp_helmdeploy.helmdeploy.invoke")
def test_list(mock_invoke):
    deployments = ["test1", "test2", "test3"]
    # With prefix
    helmdeploy.PREFIX = "test"
    releases = ["test-" + d for d in deployments] + ["foo", "bar"]
    mock_invoke.return_value = "\n".join(releases)
    assert helmdeploy.list_helm() == deployments
    # No prefix (default)
    helmdeploy.PREFIX = ""
    releases = deployments
    mock_invoke.return_value = "\n".join(releases)
    assert helmdeploy.list_helm() == deployments


def test_release_name():
    # With prefix
    helmdeploy.PREFIX = "test"
    assert helmdeploy.release_name("test") == "test-test"
    # No prefix (default)
    helmdeploy.PREFIX = ""
    assert helmdeploy.release_name("test") == "test"


@patch("subprocess.run")
def test_main(mock_run):
    helmdeploy.main(backend="memory")
    assert mock_run.call_count > 0


@patch("signal.signal")
@patch("sys.exit")
def test_terminate(mock_exit, mock_signal):
    helmdeploy.terminate(None, None)
