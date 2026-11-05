import asyncio
from sqlalchemy import String, Integer, LargeBinary, ForeignKey, Text, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import create_async_engine, AsyncAttrs

DATABASE_URL = "sqlite+aiosqlite:///school.db"

class Base(AsyncAttrs, DeclarativeBase):
    pass

class Group(Base):
    __tablename__ = "groups"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    groups_name: Mapped[str] = mapped_column(String, nullable=False)
    rasp: Mapped[str | None] = mapped_column(Text, nullable=True)

    students = relationship("Student", back_populates="group", cascade="all, delete-orphan")
    pris_records = relationship("Pris", back_populates="group", cascade="all, delete-orphan")
    violations = relationship("Narush", back_populates="group")

class Student(Base):
    __tablename__ = "student"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name_student: Mapped[str] = mapped_column(String, nullable=False)
    vector: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    id_group: Mapped[int | None] = mapped_column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=True)

    group = relationship("Group", back_populates="students")
    pris_records = relationship("Pris", back_populates="student", cascade="all, delete-orphan")
    violations = relationship("Narush", back_populates="student")

class Pris(Base):
    __tablename__ = "pris"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=True)
    student_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("student.id", ondelete="CASCADE"), nullable=True)
    data: Mapped[str | None] = mapped_column(String, nullable=True)

    group = relationship("Group", back_populates="pris_records")
    student = relationship("Student", back_populates="pris_records")
    violations = relationship("Narush", back_populates="pris")

class Classroom(Base):
    __tablename__ = "classroom"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)

    filters = relationship("Filter", back_populates="classroom", cascade="all, delete-orphan")

class Filter(Base):
    __tablename__ = "filter"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name_filter: Mapped[str | None] = mapped_column(String, nullable=True)
    classroom_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("classroom.id", ondelete="CASCADE"), nullable=True)
    activate: Mapped[int | None] = mapped_column(Integer, default=0)

    classroom = relationship("Classroom", back_populates="filters")
    anti_websites = relationship("AntiWebsite", back_populates="filter", cascade="all, delete-orphan")
    anti_apps = relationship("AntiApp", back_populates="filter", cascade="all, delete-orphan")

class AntiWebsite(Base):
    __tablename__ = "anti_website"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name_site: Mapped[str | None] = mapped_column(String, nullable=True)
    block: Mapped[int | None] = mapped_column(Integer, default=0)
    id_filter: Mapped[int | None] = mapped_column(Integer, ForeignKey("filter.id", ondelete="CASCADE"), nullable=True)

    filter = relationship("Filter", back_populates="anti_websites")

class AntiApp(Base):
    __tablename__ = "anti_app"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name_app: Mapped[str | None] = mapped_column(String, nullable=True)
    block: Mapped[int | None] = mapped_column(Integer, default=0)
    id_filter: Mapped[int | None] = mapped_column(Integer, ForeignKey("filter.id", ondelete="CASCADE"), nullable=True)

    filter = relationship("Filter", back_populates="anti_apps")

class Narush(Base):
    __tablename__ = "narush"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    anti_name: Mapped[str] = mapped_column(String, nullable=False)
    id_student: Mapped[int | None] = mapped_column(Integer, ForeignKey("student.id", ondelete="SET NULL"), nullable=True)
    time: Mapped[str | None] = mapped_column(String, nullable=True)
    id_pris: Mapped[int | None] = mapped_column(Integer, ForeignKey("pris.id", ondelete="SET NULL"), nullable=True)
    group_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("groups.id", ondelete="SET NULL"), nullable=True)

    student = relationship("Student", back_populates="violations")
    pris = relationship("Pris", back_populates="violations")
    group = relationship("Group", back_populates="violations")

class Teacher(Base):
    __tablename__ = "teachers"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    login: Mapped[str | None] = mapped_column(String, nullable=True)
    password: Mapped[str | None] = mapped_column(String, nullable=True)
    name_teacher: Mapped[str | None] = mapped_column(String, nullable=True)


async def init_models():
    engine = create_async_engine(DATABASE_URL, echo=True)
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys = ON;"))
        await conn.execute(text("PRAGMA journal_mode = WAL;"))
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print("База данных SQLite с асинхронной SQLAlchemy успешно инициализирована!")

if __name__ == "__main__":
    asyncio.run(init_models())