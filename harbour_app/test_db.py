import psycopg2

try:
    conn = psycopg2.connect(
        dbname="harbourdb",
        user="harbourdb_user",
        password="U6QKwvNHlWRhfxo9bPEUkkjq9CpiXQmf",
        host="dpg-ctkemii3esus73e7fpi0-a.singapore-postgres.render.com",
        port="5432"
    )
    print("Connection successful!")
    conn.close()
except Exception as e:
    print(f"Error: {e}")