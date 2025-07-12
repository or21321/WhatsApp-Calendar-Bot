from main import create_app
from app.models.user import db

app = create_app()
with app.app_context():
    try:
        # Add language column
        db.engine.execute('ALTER TABLE users ADD COLUMN language VARCHAR(5) DEFAULT "auto"')
        print('✅ Language column added!')
    except Exception as e:
        print(f'Language column exists or error: {e}')

    try:
        # Add conversation columns if they don't exist
        db.engine.execute('ALTER TABLE users ADD COLUMN conversation_state TEXT')
        print('✅ Conversation state column added!')
    except Exception as e:
        print(f'Conversation state column exists or error: {e}')

    try:
        db.engine.execute('ALTER TABLE users ADD COLUMN conversation_step VARCHAR(50)')
        print('✅ Conversation step column added!')
    except Exception as e:
        print(f'Conversation step column exists or error: {e}')

    try:
        db.engine.execute('ALTER TABLE users ADD COLUMN conversation_updated DATETIME')
        print('✅ Conversation updated column added!')
    except Exception as e:
        print(f'Conversation updated column exists or error: {e}')

    print('✅ Database update complete!')