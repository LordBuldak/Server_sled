import sqlite3

con = sqlite3.connect("students.db")
con.execute("PRAGMA foreign_keys = ON;")
cursor = con.cursor()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS groups (        
        id INTEGER PRIMARY KEY,
        groups_name TEXT NOT NULL, 
        rasp JSON
    )
""")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS student (
        id INTEGER PRIMARY KEY,
        name_student TEXT NOT NULL,
        vector BLOB,
        id_group INTEGER,
        FOREIGN KEY(id_group) REFERENCES groups(id) ON DELETE CASCADE
    )
""")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS pris (
        id INTEGER PRIMARY KEY,
        group_id INTEGER,
        student_id INTEGER,
        data TEXT,
        FOREIGN KEY(group_id) REFERENCES groups(id) ON DELETE CASCADE,
        FOREIGN KEY(student_id) REFERENCES student(id) ON DELETE CASCADE
    )
""")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS narush (
        id INTEGER PRIMARY KEY,
        anti_name TEXT NOT NULL,
        id_student INTEGER,
        time TEXT,
        id_pris INTEGER,
        group_id INTEGER,
        FOREIGN KEY(id_student) REFERENCES student(id) ON DELETE SET NULL,
        FOREIGN KEY(id_pris) REFERENCES pris(id) ON DELETE SET NULL,
        FOREIGN KEY(group_id) REFERENCES groups(id) ON DELETE SET NULL
    )
""")

con.commit()
con.close()

con = sqlite3.connect("protiv.db")
cur = con.cursor()

con.execute("PRAGMA foreign_keys = ON")


cur.execute(
    """
    CREATE TABLE IF NOT EXISTS classroom(
        id INTEGER PRIMARY KEY,
        name TEXT
    )
"""
)

cur.execute(
    """
    CREATE TABLE IF NOT EXISTS filter(
        id INTEGER PRIMARY KEY,
        name_filter TEXT,
        classroom_id INTEGER,
        activate INTEGER,
        FOREIGN KEY (classroom_id) REFERENCES classroom(id) ON DELETE CASCADE
    )
"""
)

cur.execute(
    """
    CREATE TABLE IF NOT EXISTS anti_website(
        id INTEGER PRIMARY KEY,
        name_site TEXT,
        block INTEGER,
        id_filter INTEGER,
        FOREIGN KEY (id_filter) REFERENCES filter(id) ON DELETE CASCADE
    )
"""
)

cur.execute(
    """
    CREATE TABLE IF NOT EXISTS anti_app(
        id INTEGER PRIMARY KEY,
        name_app TEXT,
        block INTEGER DEFAULT 0,
        id_filter INTEGER,
        FOREIGN KEY (id_filter) REFERENCES filter(id) ON DELETE CASCADE
    )
"""
)

con.commit()
con.close()

con = sqlite3.connect("teachers.db")

con.execute(
    """
        CREATE TABLE IF NOT EXISTS teachers(
            id INTEGER PRIMARY KEY, 
            login TEXT, 
            password TEXT
        , name_teacher TEXT)
            """
)
con.commit()
con.close()
