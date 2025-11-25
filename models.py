from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from contextlib import contextmanager
from lib import pybcrypt as bcrypt

CONN = 'sqlite:///siara.db'

engine = create_engine(CONN, echo = True)
Session = sessionmaker(bind=engine)
session = Session()
Base = declarative_base()

@contextmanager
def session_scope():
    Session = sessionmaker(bind=engine)
    """Provide a transactional scope around a series of operations."""
    session = Session()
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String, nullable=False)
    user_contact = Column(String)
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

class LostAnimal(Base):
    __tablename__ = 'lost_animals'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    lost_location = Column(String)
    desc_animal = Column(String)
    contato = Column(String)

    owner_id = Column(Integer, ForeignKey('users.id'), nullable=False)

    owner = relationship("User", back_populates="lost_animals")

    def set_password(self, password):

        # Generate a salt and hash the password in one step.
        password_bytes = password.encode('utf-8')
        hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
        self._password_hash = hashed.decode('utf-8') # Store the hash as a string

    def check_password(self, password):
        """
        Checks if the provided plaintext password matches the stored hash.
        Returns True if they match, False otherwise.
        """
        password_bytes = password.encode('utf-8')
        hash_bytes = self._password_hash.encode('utf-8')
        # bcrypt.checkpw safely compares the password against the hash
        return bcrypt.checkpw(password_bytes, hash_bytes)

    def __repr__(self):
        return f"<User(id={self.id}, name='{self.name}', contact='{self.user_contact}')>"

    
class FoundReport(Base):
    __tablename__ = 'found_reports'
    
    id = Column(Integer, primary_key=True)
    found_description = Column(String)
    found_location = Column(String)
    found_date = Column(String)

    finder_id = Column(Integer, ForeignKey('users.id'), nullable=False)

    finder = relationship("User", back_populates="found_reports")

    def __repr__(self):
        return f"<FoundReport(id={self.id}, found_location='{self.found_location}', finder_id={self.finder_id})>"


Base.metadata.create_all(engine)

# Example usage:

def add_sample_data():
    """Adds sample data to test the new tables and relationships."""
    print("\n--- Adding Sample Data ---")
    
    owner_user = User(name="Sarah Connor", user_contact="sc@gmail.com")
    finder_user = User(name="John Doe", user_contact="jd@yahoo.com")
    
    # 1. Sarah registers her cat as lost
    cat_mittens = LostAnimal(
        name="Mittens",
        species="Cat",
        lost_location="Elm Street, 3 days ago",
        desc_animal="Small tuxedo cat, blue eyes.",
        contato="555-CATS",
        owner=owner_user # Assign the owner
    )
    
    # 2. John registers a found dog
    found_dog_report = FoundReport(
        found_species="Dog",
        found_description="Large Black Labrador, red harness, found wandering near river.",
        found_location="River Side Park",
        finder=finder_user # Assign the finder
    )
    
    with session_scope() as session:
        session.add_all([owner_user, finder_user, cat_mittens, found_dog_report])

    print("Sample data added successfully (Sarah, John, Mittens, Found Dog Report).")

def check_relationships():
    """Verifies the relationships were created correctly."""
    print("\n--- Verifying Relationships ---")
    with session_scope() as session:
        # Check Sarah's lost animals
        sarah = session.query(User).filter_by(name="Sarah Connor").first()
        if sarah:
            print(f"Owner {sarah.name} registered animals: {[a.name for a in sarah.lost_animals]}")
            
        # Check John's found reports
        john = session.query(User).filter_by(name="John Doe").first()
        if john:
            print(f"Finder {john.name} filed reports: {[r.found_species + ' report' for r in john.found_reports]}")