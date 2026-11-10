import json
import sqlite3
import time
from contextlib import closing
from uuid import uuid4


def now_ms():
    return int(time.time() * 1000)


class Store:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with closing(self.connect()) as db, db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS missions (id TEXT PRIMARY KEY, created INTEGER NOT NULL, plan TEXT NOT NULL, items TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, updated INTEGER NOT NULL, payload TEXT NOT NULL);
            ''')
            for row in db.execute('SELECT id, payload FROM operations').fetchall():
                job = json.loads(row['payload'])
                if job['status'] in ('queued', 'running'):
                    job.update(status='failed', error='Сервер перезапущен; результат операции неизвестен', updatedAt=now_ms())
                    db.execute('UPDATE operations SET updated=?, payload=? WHERE id=?', (job['updatedAt'], json.dumps(job), row['id']))

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def save(self, plan, items):
        record = dict(missionId=uuid4().hex, createdAt=now_ms(), plan=plan, items=items)
        with closing(self.connect()) as db, db:
            db.execute('INSERT INTO missions VALUES (?, ?, ?, ?)', (record['missionId'], record['createdAt'], json.dumps(plan), json.dumps(items)))
        return record

    def mission(self, mission_id):
        with closing(self.connect()) as db:
            row = db.execute('SELECT * FROM missions WHERE id=?', (mission_id,)).fetchone()
        return None if row is None else dict(missionId=row['id'], createdAt=row['created'], plan=json.loads(row['plan']), items=json.loads(row['items']))

    def missions(self):
        with closing(self.connect()) as db:
            rows = db.execute('SELECT id,created,plan FROM missions ORDER BY created DESC LIMIT 100').fetchall()
        return [dict(missionId=row['id'], createdAt=row['created'], waypoints=len(json.loads(row['plan'])['waypoints'])) for row in rows]

    def put_operation(self, job):
        with closing(self.connect()) as db, db:
            db.execute('INSERT OR REPLACE INTO operations VALUES (?, ?, ?)', (job['operationId'], job['updatedAt'], json.dumps(job)))

    def operation(self, operation_id):
        with closing(self.connect()) as db:
            row = db.execute('SELECT payload FROM operations WHERE id=?', (operation_id,)).fetchone()
        return json.loads(row['payload']) if row else None
