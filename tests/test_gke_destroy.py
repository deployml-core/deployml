"""Unit tests for the GKE teardown disk-reclaim logic.

Covers the fix for the orphaned PersistentDisk left by gke-destroy
--delete-cluster: the in-cluster CSI driver reclaims a PVC's backing PD
asynchronously, and deleting the cluster too soon orphans a billing disk. No real
GCP or kubectl calls; run_tool is mocked at the boundary.
"""

from types import SimpleNamespace
from unittest.mock import patch

import deployml.utils.kubernetes_gke as gke


# ---------- disk_ref_from_volume_handle (pure parsing) ----------


def test_disk_ref_from_zonal_volume_handle():
    h = "projects/my-proj/zones/us-west1-a/disks/pvc-1234"
    assert gke.disk_ref_from_volume_handle(h) == ("pvc-1234", "--zone", "us-west1-a")


def test_disk_ref_from_regional_volume_handle():
    h = "projects/my-proj/regions/us-west1/disks/pvc-abcd"
    assert gke.disk_ref_from_volume_handle(h) == ("pvc-abcd", "--region", "us-west1")


def test_disk_ref_from_volume_handle_none_for_garbage():
    assert gke.disk_ref_from_volume_handle("") is None
    assert gke.disk_ref_from_volume_handle("not-a-handle") is None
    assert gke.disk_ref_from_volume_handle(None) is None


# ---------- get_pvc_volume_handle (boundary mocked) ----------


def test_get_pvc_volume_handle_returns_handle_when_bound():
    def fake_run_tool(name, args, **kw):
        if args[:2] == ["get", "pvc"]:
            return SimpleNamespace(returncode=0, stdout="pv-xyz\n", stderr="")
        if args[:2] == ["get", "pv"]:
            return SimpleNamespace(
                returncode=0, stdout="projects/p/zones/z/disks/pvc-1\n", stderr=""
            )
        raise AssertionError(f"unexpected call {args}")

    with patch.object(gke, "run_tool", side_effect=fake_run_tool):
        assert (
            gke.get_pvc_volume_handle("mlflow-pvc") == "projects/p/zones/z/disks/pvc-1"
        )


def test_get_pvc_volume_handle_none_when_unbound():
    with patch.object(
        gke,
        "run_tool",
        return_value=SimpleNamespace(returncode=0, stdout="", stderr=""),
    ):
        assert gke.get_pvc_volume_handle("mlflow-pvc") is None


# ---------- delete_gce_disk_if_exists (boundary mocked) ----------


def test_delete_gce_disk_skips_when_already_gone():
    """If the CSI driver already reclaimed the disk, describe fails and no delete
    must be issued."""
    calls = []

    def fake_run_tool(name, args, **kw):
        calls.append(args)
        return SimpleNamespace(returncode=1, stdout="", stderr="NOT_FOUND")

    with patch.object(gke, "run_tool", side_effect=fake_run_tool):
        ok = gke.delete_gce_disk_if_exists("my-proj", ("pvc-1", "--zone", "us-west1-a"))
    assert ok is True
    assert all(a[:3] != ["compute", "disks", "delete"] for a in calls)


def test_delete_gce_disk_deletes_when_present():
    seq = [
        SimpleNamespace(returncode=0, stdout="pvc-1\n", stderr=""),  # describe: found
        SimpleNamespace(returncode=0, stdout="", stderr=""),  # delete
        SimpleNamespace(returncode=1, stdout="", stderr="NOT_FOUND"),  # describe: gone
    ]
    calls = []

    def fake_run_tool(name, args, **kw):
        calls.append(args)
        return seq.pop(0)

    with patch.object(gke, "run_tool", side_effect=fake_run_tool):
        ok = gke.delete_gce_disk_if_exists("my-proj", ("pvc-1", "--zone", "us-west1-a"))
    assert ok is True
    assert any(a[:3] == ["compute", "disks", "delete"] for a in calls)
