from flask import Flask, render_template, request, redirect, url_for, session, send_file
import os
import sqlite3
from werkzeug.security import check_password_hash, generate_password_hash
import re
from datetime import datetime
from io import BytesIO

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'секретно-секретный секрет')

def db_connect():
    conn = sqlite3.connect('web-prog-labs-2/efimkinargz/rgz/database.db')
    conn.row_factory = sqlite3.Row 
    cur = conn.cursor()
    return conn, cur

@app.route("/")
def index():
    return render_template("index.html", login=session.get("username"))

@app.route("/dating", methods=["GET"])
def dating():
    user_id = session.get("user_id")

    page = int(request.args.get("page", 1))
    per_page = 3

    conn, cur = db_connect()

    # Получаем данные текущего пользователя
    cur.execute("SELECT gender, seeking FROM users WHERE id = ?", (user_id,))
    user_data = cur.fetchone()
    current_user = {"gender": user_data["gender"], "seeking": user_data["seeking"]} 

    # Запрос пользователей, которые соответствуют критериям
    cur.execute(""" 
        SELECT id, name, gender, about, photo, birth_date 
        FROM users 
        WHERE active = TRUE AND gender = ? AND seeking = ? 
        LIMIT ? OFFSET ? 
    """, (current_user["seeking"], current_user["gender"], per_page, (page - 1) * per_page))

    users = cur.fetchall()

    # Вычисление возраста
    today = datetime.today()
    updated_users = []

    for user in users:
        user_dict = dict(user)  # Преобразуем Row в обычный словарь
        birth_date_obj = datetime.strptime(user_dict['birth_date'], "%Y-%m-%d")
        age = today.year - birth_date_obj.year - ((today.month, today.day) < (birth_date_obj.month, birth_date_obj.day))
        user_dict['age'] = age
        updated_users.append(user_dict)

    # Подготовка пагинации
    next_page = page + 1 if len(users) == per_page else None

    cur.close()
    conn.close()

    return render_template("dating.html", users=updated_users, page=page, next_page=next_page)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login = request.form["username"]
        password = request.form["password"]

        conn, cur = db_connect()
        cur.execute("SELECT * FROM users WHERE login = ?", (login,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["username"] = user["login"]
            return redirect(url_for("index"))
        return "Неверные логин или пароль"
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop('username', None)
    session.pop('user_id', None)
    return redirect(url_for("index"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        login = request.form['login']
        password = generate_password_hash(request.form['password'])
        name = request.form.get("name", "").strip()
        gender = request.form.get("gender", "").strip()
        looking_for = request.form.get("looking_for", "").strip()
        birth_date = request.form.get("birth_date", "").strip()
        about = request.form.get("about", "").strip()
        active = request.form.get("active") == "on" 
        photo = request.files.get("photo")

        if not login or not password:
            return "Логин и пароль обязательны"
        if not re.match(r"^[a-zA-Z0-9_.-]+$", login):
            return "Логин должен состоять из латинских букв, цифр, знаков препинания"

        conn, cur = db_connect()
        cur.execute("SELECT id FROM users WHERE login = ?", (login,))
        if cur.fetchone():
            cur.close()
            conn.close()
            return "Логин уже занят"

        # Обработка фотографии
        photo_binary = None
        if photo and photo.filename:
            photo_binary = photo.read()  # Чтение файла в бинарный формат

        # Вставка данных в базу
        cur.execute(""" 
            INSERT INTO users (login, password, name, gender, seeking, birth_date, about, photo, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) 
        """, (login, password, name, gender, looking_for, birth_date, about, photo_binary, active))
        conn.commit()
        cur.close()
        conn.close()

        return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/photo/<int:user_id>")
def get_photo(user_id):
    conn, cur = db_connect()
    cur.execute("SELECT photo FROM users WHERE id = ?", (user_id,))
    user = cur.fetchone()
    cur.close()
    conn.close()

    if user and user["photo"]:
        image_data = user["photo"]
        image_stream = BytesIO(image_data)
        return send_file(image_stream, mimetype='image/jpeg')
    else:
        return "Фото не найдено", 404

@app.route("/profile", methods=["GET", "POST"])
def profile():
    user_id = session.get("user_id")

    if not user_id:
        return redirect(url_for("login"))

    conn, cur = db_connect()
    cur = conn.cursor()

    # Извлекаем данные о пользователе из базы
    cur.execute("SELECT id, login, name, gender, seeking, birth_date, about, photo, active FROM users WHERE id = ?", (user_id,))
    user_data = cur.fetchone()

    if not user_data:
        cur.close()
        conn.close()
        return "Пользователь не найден", 404

    # Обработка формы редактирования
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        gender = request.form.get("gender", "").strip()
        looking_for = request.form.get("looking_for", "").strip()
        birth_date = request.form.get("birth_date", "").strip()
        about = request.form.get("about", "").strip()
        active = request.form.get("active") == "on"  # Для чекбокса
        photo = request.files.get("photo")

        # Обработка фотографии: если фото не загружено, оставляем старое
        photo_binary = user_data["photo"]  # Изначально присваиваем старую фотографию
        if photo and photo.filename:
            photo_binary = photo.read()  # Чтение нового фото в бинарный формат

        # Обновление данных пользователя в базе данных
        cur.execute("""
            UPDATE users 
            SET name = ?, gender = ?, seeking = ?, birth_date = ?, about = ?, photo = ?, active = ?
            WHERE id = ?
        """, (name, gender, looking_for, birth_date, about, photo_binary, active, user_id))
        conn.commit()

        # Обновляем данные пользователя
        cur.execute("SELECT id, login, name, gender, seeking, birth_date, about, photo, active FROM users WHERE id = ?", (user_id,))
        user_data = cur.fetchone()

    # Закрываем соединение с базой
    cur.close()
    conn.close()

    return render_template("profile.html", user=user_data)


@app.route("/delete_profile", methods=["POST"])
def delete_profile():
    user_id = session.get("user_id")

    conn, cur = db_connect()
    cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()

    cur.close()
    conn.close()

    session.pop('username', None)
    session.pop('user_id', None)

    return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=True)
