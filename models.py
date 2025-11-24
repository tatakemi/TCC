from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

CONN = 'sqlite:///siara.db'

engine = create_engine(CONN, echo = True)
Session = sessionmaker(bind=engine)
session = Session()
Base = declarative_base()

class Animal(Base):
    __tablename__ = 'animals'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    lost_location = Column(String)
    desc_animal = Column(String)
    
    
Base.metadata.create_all(engine)