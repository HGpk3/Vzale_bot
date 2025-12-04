import sqlite3

def init_database():
    conn = sqlite3.connect("tournament.db")
    cursor = conn.cursor()

    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            team TEXT
        )
    ''')

    # Таблица команд
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_name TEXT,
            member_id INTEGER,
            member_name TEXT
        )
    ''')

    # Таблица свободных игроков
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS free_agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            info TEXT
        )
    ''')

    conn.commit()
    conn.close()
    print("База данных tournament.db успешно инициализирована.")

if __name__ == "__main__":
    init_database()
