from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from contextlib import contextmanager
# Use system bcrypt (install with pip install bcrypt)
import bcrypt

CONN = 'sqlite:///siara.db'

engine = create_engine(CONN, echo=True)
Session = sessionmaker(bind=engine)
session = Session()
Base = declarative_base()

@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""
    SessionLocal = sessionmaker(bind=engine)
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except:
        s.rollback()
        raise
    finally:
        s.close()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String, nullable=False, unique=True)
    contact = Column(String)
    _password_hash = Column(String, nullable=False)

    lost_animals = relationship(
        "LostAnimal",
        back_populates="owner",
        cascade="all, delete-orphan"
    )
    found_reports = relationship(
        "FoundReport",
        back_populates="finder",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}')>"

    def set_password(self, password: str):
        password_bytes = password.encode('utf-8')
        hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
        self._password_hash = hashed.decode('utf-8')

    def check_password(self, password: str) -> bool:
        password_bytes = password.encode('utf-8')
        if not self._password_hash:
            return False
        hash_bytes = self._password_hash.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hash_bytes)

class LostAnimal(Base):
    __tablename__ = 'lost_animals'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    species = Column(String)
    lost_location = Column(String)
    desc_animal = Column(String)
    contact = Column(String)

    # new location fields
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    owner_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    owner = relationship("User", back_populates="lost_animals")

    def __repr__(self):
        return f"<LostAnimal(id={self.id}, name='{self.name}', owner_id={self.owner_id})>"

class FoundReport(Base):
    __tablename__ = 'found_reports'
    id = Column(Integer, primary_key=True)
    species = Column(String)
    found_description = Column(String)
    found_location = Column(String)
    found_date = Column(String)

    # new location fields
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    finder_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    finder = relationship("User", back_populates="found_reports")

    def __repr__(self):
        return f"<FoundReport(id={self.id}, found_location='{self.found_location}', finder_id={self.finder_id})>"

# Ensure tables exist / create new columns for newly created DBs
Base.metadata.create_all(engine)