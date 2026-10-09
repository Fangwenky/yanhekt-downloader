"""Persistent course tracking and local recording inventory (no network calls)."""
import json
import re
from pathlib import Path

from yanhe import STREAM_NAMES


def write_json(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.chmod(0o600)
    temp.replace(path)


class Library:
    def __init__(self, directory):
        self.path = Path(directory) / 'library.json'
        self.data = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
        for key, default in [('courses', []), ('replays', {}), ('tracked', {}), ('files', {}), ('last_check', 0)]:
            self.data.setdefault(key, default)

    def save(self):
        write_json(self.path, self.data)

    def scan(self, outdir, jobs):
        records = self.data['files']
        for job in jobs:
            if job['status'] == 'done':
                key = f"{job['course_id']}:{job['sub_id']}:{job['stream']}"
                records[key] = {k: job[k] for k in ['course_id', 'sub_id', 'stream', 'course', 'title', 'path']}
        names = {label: kind for kind, label in STREAM_NAMES.items()}
        pattern = re.compile(r'^(.*)_(\d+)_(教师画面|PPT画面|学生画面)\.mp4$', re.I)
        for file in Path(outdir).rglob('*.mp4'):
            match = pattern.match(file.name)
            course = re.match(r'^(.*)_(\d+)$', file.parent.name)
            if not match or not course:
                continue
            title, sid, label = match.groups()
            cname, cid = course.groups()
            key = f'{cid}:{sid}:{names[label]}'
            records[key] = dict(course_id=cid, sub_id=sid, stream=names[label], course=cname, title=title, path=str(file.resolve()))
        for record in records.values():
            file = Path(record['path'])
            record['exists'] = file.is_file() and file.stat().st_size > 0
            if record['exists']:
                record.update(bytes=file.stat().st_size, saved_at=file.stat().st_mtime)
        self.save()
        return sum(record['exists'] for record in records.values())

    def file(self, cid, sid, kind):
        row = self.data['files'].get(f'{cid}:{sid}:{kind}')
        return row if row and Path(row['path']).is_file() and Path(row['path']).stat().st_size > 0 else None

    def decorate(self, cid, rows, jobs):
        result = []
        for row in rows:
            files = [self.file(cid, row['id'], kind) for kind in STREAM_NAMES]
            files = [item for item in files if item]
            tasks = {j['stream']: j['status'] for j in jobs if j['course_id'] == cid and j['sub_id'] == row['id']}
            result.append(dict(row, files=files, downloaded=[f['stream'] for f in files], tasks=tasks,
                               is_new=row.get('is_new', False) and not files))
        return result

    def update_replays(self, cid, rows):
        previous = {r['id']: r for r in self.data['replays'].get(cid, [])}
        known = cid in self.data['replays']
        for row in rows:
            before = previous.get(row['id'])
            row['is_new'] = bool(row['ready'] and ((known and (not before or not before['ready'])) or (before and before.get('is_new'))))
        self.data['replays'][cid] = rows
        self.save()

    def summaries(self, jobs):
        result = []
        for course in self.data['courses']:
            cid = course['id']
            follow = self.data['tracked'].get(cid)
            kinds = follow['streams'] if follow else ['teacher']
            rows = self.decorate(cid, self.data['replays'].get(cid, []), jobs)
            ready = [r for r in rows if r['ready']]
            pending = [r for r in ready if any(kind not in r['downloaded'] for kind in kinds)]
            result.append(dict(course, tracked=bool(follow), auto_download=bool(follow and follow['auto_download']),
                               streams=kinds,
                               ready_count=len(ready), downloaded_count=sum(bool(r['downloaded']) for r in rows),
                               pending_count=len(pending), new_count=sum(r['is_new'] for r in pending),
                               checked=cid in self.data['replays']))
        return result
