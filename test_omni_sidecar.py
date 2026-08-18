import json
import os
import sqlite3
import tempfile
from pathlib import Path


def make_db(path):
    conn = sqlite3.connect(path)
    conn.executescript('''
      CREATE TABLE video_index(video_key TEXT PRIMARY KEY, title TEXT, creator TEXT,
        duration REAL, moment_count INTEGER, created_at REAL);
      CREATE TABLE graph_nodes(id TEXT PRIMARY KEY, kind TEXT, label TEXT, sub TEXT,
        weight REAL, meta TEXT);
      CREATE TABLE graph_edges(src TEXT, dst TEXT, rel TEXT, weight REAL, ref TEXT,
        PRIMARY KEY(src,dst,rel));
    ''')
    conn.execute("INSERT INTO video_index VALUES ('8','Video #8','David',17.6,8,1)")
    conn.execute("INSERT INTO graph_nodes VALUES ('v:8','video','Video #8','videos',3,'{}')")
    conn.execute("INSERT INTO graph_nodes VALUES ('creator:David','creator','David','creators',1,'{}')")
    conn.execute("INSERT INTO graph_edges VALUES ('v:8','creator:David','created_by',1,'creators')")
    conn.commit(); conn.close()


def main():
    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / 'atlas.db')
        make_db(db_path)
        os.environ['VIOS_ATLAS_DB_PATH'] = db_path
        import omni_dashboard_sidecar as sidecar
        client = sidecar.app.test_client()
        health = client.get('/api/health').get_json()
        assert health['ready'] is True and health['mode'] == 'dashboard-only'
        videos = client.get('/api/videos').get_json()
        assert videos[0]['video_uuid'] == '8'
        assert videos[0]['dashboard_only'] is True
        assert videos[0]['stage'] == 'atlas-read-only'
        assert videos[0]['evidence_count'] == videos[0]['moment_count']
        graph = client.get('/api/neo4j/graph').get_json()
        assert len(graph['nodes']) == 2 and len(graph['edges']) == 1
        assert client.get('/').status_code == 200
    print('Omni sidecar tests passed')


if __name__ == '__main__':
    main()
