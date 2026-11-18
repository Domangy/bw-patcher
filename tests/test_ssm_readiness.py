from pathlib import Path
import json

from bwpatcher.ssm_readiness import build_report, check_image, main


def test_no_originals_never_claims_flashable(tmp_path):
    report = build_report(tmp_path)
    assert report["model"] == "xiaomi.scooter.5pro"
    assert report["release_ready"] is False
    assert report["flashable_ssm_image_available"] is False
    assert report["originals_verified"] is False
    assert all(not image["exists"] for image in report["images"].values())


def test_unrelated_binary_is_not_accepted(tmp_path):
    path = tmp_path / "mcu_0007.bin"
    path.write_bytes(b"arbitrary file, not scooter firmware")
    result = check_image(path, "mcu")
    assert result["exists"] is True
    assert result["original_verified"] is False
    assert "nicht" in result["reason"].lower()


def test_report_is_json_and_does_not_create_firmware(tmp_path, capsys):
    out = tmp_path / "status.json"
    assert main(["--originale", str(tmp_path), "--output", str(out)]) == 0
    on_disk = json.loads(out.read_text(encoding="utf-8"))
    on_stdout = json.loads(capsys.readouterr().out)
    assert on_disk == on_stdout
    assert on_disk["release_ready"] is False
    assert list(tmp_path.iterdir()) == [out]


def test_readiness_has_explicit_unresolved_blockers(tmp_path):
    report = build_report(tmp_path)
    assert not report["ssm_integrated_in_real_firmware"]
    assert not report["hardware_validated"]
    assert len(report["blocking_reasons"]) >= 3
