from pathlib import Path
import base64
import gzip
import json
import os
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas import maps, ingest
from vios.process import intake as process_intake
from vios.process import engine as engine_module
from vios.process.engine import ProcessEngine


def test_terms_value_is_defensive():
    assert maps._terms_value(None) == []
    assert maps._terms_value('["person", "screen"]') == ["person", "screen"]
    assert maps._terms_value('plain legacy label') == ['plain legacy label']
    assert maps._terms_value('{broken') == ['{broken']


def test_map_meta_skips_malformed_rows():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    maps.ensure_schema(conn)
    conn.execute(
        "INSERT INTO map_point(level, ref, video_key, x, y, cluster, t_start, source) "
        "VALUES ('video','v1','v1',0,0,0,0,'visual')")
    conn.execute(
        "INSERT INTO map_cluster(level, cluster, label, terms, size, videos, cx, cy) "
        "VALUES (?,?,?,?,?,?,?,?)",
        ('video', 0, 'good', json.dumps(['visual']), 1, 1, 0, 0))
    conn.execute(
        "INSERT INTO map_cluster(level, cluster, label, terms, size, videos, cx, cy) "
        "VALUES ('video','bad','legacy','not-json','bad','bad','bad','bad')")
    conn.commit()
    out = maps.meta(conn, 'video')
    assert out['ok'] is True
    assert out['count'] == 1
    assert len(out['clusters']) == 1
    assert out['clusters'][0]['terms'] == ['visual']


def test_multipart_shard_name_is_logical_and_ordered():
    name = process_intake.shard_name('site-0001.part002of003')
    assert process_intake.shard_part_from_name(name) == {
        'shard_id': 'site-0001', 'index': 2, 'total': 3}
    assert process_intake.shard_part_from_name(
        process_intake.shard_name('site-0002')) == {
            'shard_id': 'site-0002', 'index': 1, 'total': 1}


def test_process_engine_splits_gzip_shards_on_jsonl_boundaries():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, 'evidence.jsonl.gz')
        header = json.dumps({'_': 'vios-evidence-shard', 'schema': 3}) + '\n'
        rows = [json.dumps({'t': 'claim',
                            'value': base64.b64encode(os.urandom(180)).decode()})
                 + '\n' for _ in range(30)]
        with gzip.open(path, 'wt', encoding='utf-8') as fh:
            fh.write(header)
            fh.writelines(rows)
        old = engine_module.SHARD_PART_BYTES
        engine_module.SHARD_PART_BYTES = 64
        try:
            parts = ProcessEngine._split_shard(object(), path)
        finally:
            engine_module.SHARD_PART_BYTES = old
        assert len(parts) > 1
        rebuilt = []
        for part in parts:
            with gzip.open(part, 'rt', encoding='utf-8') as fh:
                lines = fh.readlines()
            assert json.loads(lines[0])['_'] == 'vios-evidence-shard'
            rebuilt.extend(lines[1:])
            assert os.path.getsize(part) < 50 * 1024 * 1024
        assert rebuilt == rows


def test_map_readers_use_named_rows_on_shared_connection():
    conn = ingest.connect(':memory:')
    maps.ensure_schema(conn)
    conn.execute(
        "INSERT INTO map_point(level, ref, video_key, x, y, cluster, t_start, source) "
        "VALUES ('video','v1','v1',0.25,0.75,2,NULL,NULL)")
    conn.commit()
    refs = maps.refs(conn, 'video')
    points = maps.points_binary(conn, 'video')
    assert refs['count'] == 1
    assert refs['refs'] == ['v1']
    assert len(points) == 12
    conn.close()


def test_caption_asset_manifest_is_detected():
    assert ingest._looks_like_asset_manifest({
        'file_name': None, 'caption': 'manifest · vios:8'})
    assert ingest._looks_like_asset_manifest({
        'file_name': '8-manifest.json', 'caption': ''})
    assert not ingest._looks_like_asset_manifest({
        'file_name': '8.json', 'caption': 'meta · vios:8'})


def test_hotfix_contracts_are_present():
    engine = (ROOT / 'vios/process/engine.py').read_text()
    audio = (ROOT / 'vios/process/runners/audio.py').read_text()
    server = (ROOT / 'atlas/server.py').read_text()
    media = (ROOT / 'atlas/media.py').read_text()
    js = (ROOT / 'atlas/web/atlas.js').read_text()
    css = (ROOT / 'atlas/web/atlas.css').read_text()
    omni = (ROOT / 'omni_dashboard.html').read_text()
    process_ui = (ROOT / 'process_ui.html').read_text()
    assert 'VIOS_STAGE_SNAPSHOT_ONLY_FINAL' in engine
    assert 'stage still has queued/running work' in engine
    assert 'Pipeline.from_pretrained(job.component.model, token=token)' in audio
    assert 'pyannote weights are gated or the HF token lacks access' in audio
    assert 'def _reconcile_boot' in server
    assert 'poster-missing' in js
    assert 'ATLAS_POSTER_FALLBACK_WAIT' in media
    assert 'width:100vw' in css and 'height:100dvh' in css
    assert '.player-idle[hidden], .player-live[hidden]' in css
    assert 'indexed evidence' in omni and 'frames not reported' in omni
    assert 'withPlanFallback' in process_ui and 'planSnapshot' in process_ui


if __name__ == '__main__':
    test_terms_value_is_defensive()
    test_map_meta_skips_malformed_rows()
    test_multipart_shard_name_is_logical_and_ordered()
    test_process_engine_splits_gzip_shards_on_jsonl_boundaries()
    test_map_readers_use_named_rows_on_shared_connection()
    test_caption_asset_manifest_is_detected()
    test_hotfix_contracts_are_present()
    print('live hotfix tests passed')
