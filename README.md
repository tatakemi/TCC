A system to help locate, rescue, register and adopt lost, abandoned or stray animals.
This application aims to support the community in identifying and assisting animals in vulnerable situations.
Users can create accounts, report animals, view nearby cases and help reunite pets with their guardians or support rescue actions.

REQUIREMENTS: python, flet, sqlalchemy, bcrypt, geopy

FEATURES:
  User Management:
    Account creation
    Secure login
    Password hashing with bcrypt
  
  Animal Management:
    Register lost, abandoned or found animals
    Track animal location using geopy
    List animals and filter cases
    View detailed information about each animal
  
  Geolocation & Tracking:
    Approximate address → coordinates using geopy
    Potential future support for maps
  
  Interface (Flet):
    Multi-page UI using Flet and route navigation
    Login page
    Registration page
    Dashboard
    Animal pages (list, create, details, delete)
    
  Database:
    SQLite database
    ORM with SQLAlchemy
    Tables for users and animals
    Database migrations possible in future versions
