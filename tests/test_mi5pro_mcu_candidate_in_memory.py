"""In-memory MCU ES32 wrapper tests; never upload or export."""
from hashlib import sha256
from pathlib import Path
import os

import pytest

from bwpatcher.mi5pro_mcu_candidate_in_memory import (
    McuResearchCandidateEmulator,
    build_mcu_research_candidate,
)
from bwpatcher.mi5pro_integration import McuOriginal
from bwpatcher.ssm_firmware import ORIGINALS, inspect_mcu
from bwpatcher.mi5pro_research import AnalysisError


@pytest.fixture(scope="module")
def original():
    directory = os.environ.get("MI5PRO_FIRMWARE_DIR")
    if not directory:
        pytest.skip("Firmwaredateien nur lokal, nicht im Repository.")
    return (Path(directory) / "mcu_0007.bin").read_bytes()


@pytest.fixture(scope="module")
def candidate(original):
    return build_mcu_research_candidate(original)


def test_experimental_mcu_is_complete_wrapper_with_consistent_crc(original,candidate):
    assert len(candidate.image) == len(original) == 149504
    assert sha256(original).hexdigest() == ORIGINALS["mcu"]["sha256"]
    assert sha256(candidate.image).hexdigest() != ORIGINALS["mcu"]["sha256"]
    assert candidate.crc_valid
    report = inspect_mcu(candidate.image)
    assert report["checksums_valid"]
    assert report["es_header_offset"]==0x19800
    assert report["es_code_offset"]==0x19880
    assert report["es_code_size"]==0xAEB0
    assert candidate.stub_runtime_address==0xAE90
    assert candidate.stub_length==20
    assert candidate.safe_to_flash is False
    assert candidate.on_device_tested is False
    assert candidate.firmware_authentication_proven is False


def test_emulator_executes_code_as_embedded_in_actual_container(original,candidate):
    stock = McuOriginal(original)
    modified = McuResearchCandidateEmulator(original,candidate)
    baseline = stock.select_limits(b"60556")
    region = modified.select_limits(b"60556")
    assert region == baseline
    for mode in (11,2,3):
        assert modified.speed_selection(mode)==stock.speed_selection(mode)
    assert stock.speed_selection(4)==208
    assert modified.speed_selection(4)==627
    assert modified.read(0x2000177C,2) == (627).to_bytes(2,"little")


def test_original_file_and_other_payload_bytes_unchanged(original,candidate):
    original = bytes(original)
    out = candidate.image
    touched = {i for i,(x,y) in enumerate(zip(original,out)) if x!=y}
    allowed = (
        set(range(0x0A,0x0C)) |
        set(range(0x19806,0x19808)) |
        set(range(0x19830,0x19832)) |
        set(range(0x1D0D6,0x1D0DA)) |
        set(range(0x24710,0x24710+candidate.stub_length))
    )
    assert touched <= allowed
    assert len(touched)>10


def test_invalid_mcu_image_refused():
    with pytest.raises(AnalysisError):
        build_mcu_research_candidate(b"not firmware")
