from sqlalchemy import inspect, text
from src.config.database import Base, engine
from src import models
JOB_COLUMNS = {
    'stall': "ALTER TABLE jobs ADD COLUMN stall VARCHAR(120) NOT NULL DEFAULT ''",
    'superseded': "ALTER TABLE jobs ADD COLUMN superseded BOOLEAN NOT NULL DEFAULT 0",
    'rejection': "ALTER TABLE jobs ADD COLUMN rejection JSON NULL",
}
def migrate():
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        existing = {c['name'] for c in inspect(conn).get_columns('jobs')}
        for name, ddl in JOB_COLUMNS.items():
            if name not in existing:
                conn.execute(text(ddl))
if __name__=='__main__':migrate()
