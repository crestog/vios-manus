from vios.process.contracts import (
    AssetRef,
    ArtifactRef,
    EvidenceMoment,
    JobRef,
    JobState,
    OperationRef,
    OperationState,
    ProjectionRef,
    ResourceContract,
    serialize_contract,
)


def test_asset_identity_is_stable():
    a = AssetRef.from_source(channel="chan", message_id="7", sha256="abc",
                             filename="x.mp4")
    b = AssetRef.from_source(channel="chan", message_id="7", sha256="abc",
                             filename="x.mp4")
    assert a.asset_id == b.asset_id
    assert a.asset_id.startswith("asset_")


def test_job_identity_is_idempotent_and_resource_validates():
    resource = ResourceContract(resource_class="gpu_inference", gpu_count=1,
                                gpu_index=0, vram_mb=4096, batch_size=8)
    first = JobRef.create(operation_id="op", asset_id="asset", component="clip",
                          generation_id="g1", resource=resource,
                          input_refs=["frames:a"])
    second = JobRef.create(operation_id="op-other", asset_id="asset",
                           component="clip", generation_id="g1", resource=resource,
                           input_refs=["frames:a"])
    assert first.job_id == second.job_id
    assert first.state is JobState.CREATED


def test_invalid_resource_is_rejected():
    try:
        ResourceContract(gpu_count=0, gpu_index=0).validate()
    except ValueError as exc:
        assert "gpu_index" in str(exc)
    else:
        raise AssertionError("invalid GPU resource was accepted")


def test_evidence_moment_has_stable_identity_and_temporal_bounds():
    m = EvidenceMoment.create(asset_id="asset", corpus_id="c",
                              generation_id="g", start_sec=1.23456,
                              end_sec=4.56789, modality="visual",
                              evidence_type="scene", text="a room")
    assert m.moment_id.startswith("moment_")
    assert m.start_sec < m.end_sec
    try:
        EvidenceMoment.create(asset_id="asset", corpus_id="c",
                              generation_id="g", start_sec=2, end_sec=1,
                              modality="visual", evidence_type="scene")
    except ValueError:
        pass
    else:
        raise AssertionError("backwards temporal interval was accepted")


def test_operation_and_projection_serialize():
    op = OperationRef.create(profile="search", generation_id="g")
    op.state = OperationState.SEARCHABLE
    op.heartbeat("index")
    data = serialize_contract(op)
    assert data["state"] == "searchable"
    assert data["current_stage"] == "index"

    artifact = ArtifactRef.for_output("asset", "frames", "g")
    projection = ProjectionRef.create(name="atlas_fts", generation_id="g",
                                      source_artifact_refs=[artifact.artifact_id])
    out = serialize_contract(projection)
    assert out["projection_id"].startswith("projection_")
    assert out["source_artifact_refs"] == [artifact.artifact_id]
