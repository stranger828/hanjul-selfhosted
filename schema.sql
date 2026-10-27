PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS folders (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS notes (
 id TEXT PRIMARY KEY, title TEXT NOT NULL DEFAULT '', body TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, tags TEXT NOT NULL DEFAULT '[]',
 starred INTEGER NOT NULL DEFAULT 0, archived INTEGER NOT NULL DEFAULT 0,
 deleted INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1,
 folder_id TEXT REFERENCES folders(id)
);
CREATE INDEX IF NOT EXISTS notes_state_date ON notes(deleted, archived, updated_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS notes_date ON notes(deleted, updated_at DESC, id DESC);
CREATE TABLE IF NOT EXISTS attachments (
 id TEXT PRIMARY KEY, note_id TEXT NOT NULL REFERENCES notes(id), name TEXT NOT NULL,
 mime TEXT NOT NULL, data BLOB NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS attachment_note ON attachments(note_id);
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(title, body, content='notes', content_rowid='rowid', tokenize='trigram');
CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
 INSERT INTO notes_fts(rowid,title,body) VALUES(new.rowid,new.title,new.body);
END;
CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
 INSERT INTO notes_fts(notes_fts,rowid,title,body) VALUES('delete',old.rowid,old.title,old.body);
END;
CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN
 INSERT INTO notes_fts(notes_fts,rowid,title,body) VALUES('delete',old.rowid,old.title,old.body);
 INSERT INTO notes_fts(rowid,title,body) VALUES(new.rowid,new.title,new.body);
END;
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (hash TEXT PRIMARY KEY, csrf TEXT NOT NULL, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS tokens (id TEXT PRIMARY KEY, name TEXT NOT NULL, hash TEXT NOT NULL UNIQUE, scope TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS imports (id TEXT PRIMARY KEY, data BLOB NOT NULL, expires REAL NOT NULL);
