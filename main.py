from flask import (
    Flask,
    request,
    jsonify,
    render_template,
    redirect,
    request,
    session,
    flash,
    url_for,
)
import datetime
import sqlite3
import numpy as np
import dlib
from skimage import io
import os
import json
import subprocess
import hashlib

rocess1 = subprocess.Popen(["py", "init_db.py"])
app = Flask(__name__)
app.secret_key = b'_5#y2L"F4Q8z\n\xec]/'
app.config["UPLOAD_FOLDER"] = "static/photos"
app.config["ALLOWED_EXTENSIONS"] = {"png", "jpg", "jpeg", "gif"}
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
ADMIN_CREDENTIALS = {
    "username": "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918",
    "password": "44ac9a7d1fed334c2d41c75d56e33e04857988f767ae4fccac6b6b1799dd8f80",
}
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
model = dlib.shape_predictor("shape_predictor_68_face_landmarks.dat")  # type: ignore
facerec = dlib.face_recognition_model_v1("dlib_face_recognition_resnet_model_v1.dat")  # type: ignore
detector = dlib.get_frontal_face_detector()  # type: ignore
sp = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]


def hash_func(s: str):
    return hashlib.sha256(s.encode()).hexdigest()


def allowed_file(filename: str):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]
    )


def is_logged_in():
    return session.get("is_login") is True


@app.route("/upload", methods=["POST"])
def upload_data():
    data = request.json
    con = sqlite3.connect("students.db")
    a = con.execute("""SELECT id_group FROM student WHERE id = ?""", [data]).fetchone()
    con.execute(
        """
     INSERT INTO pris(group_id, student_id, data) 
      VALUES (?,?,?)
""",
        [a[0], data, datetime.date.today().strftime("%Y-%m-%d")],
    )
    con.commit()
    con.close()
    return jsonify({"status": "success"})


@app.route("/not_rasp_player", methods=["POST"])
def not_rasp_player():
    try:
        data = request.get_json()
        if not isinstance(data, list) or len(data) < 2:
            return (
                jsonify(
                    {"status": "error", "msg": "Expected list with at least 2 elements"}
                ),
                400,
            )

        name = str(data[0]).strip() or "Неизвестный"
        hostname = str(data[1]).strip()

        today = datetime.date.today().strftime("%Y-%m-%d")
        now_time = datetime.datetime.now().strftime("%H:%M")

        new_record = [name, hostname, today, now_time]

        try:
            with open("data.json", "r", encoding="utf-8") as f:
                records = json.load(f)
            if not isinstance(records, list):
                records = [[0]]
        except (FileNotFoundError, json.JSONDecodeError):
            records = [[0]]
        if records == []:
            records = [[0]]
        new_record = [max(map(lambda x: x[0], records)) + 1] + new_record
        records.append(new_record)  # type: ignore

        cutoff = datetime.date.today() - datetime.timedelta(days=7)
        cutoff_str = cutoff.strftime("%Y-%m-%d")
        records = [
            r
            for r in records
            if len(r) >= 4 and isinstance(r[2], str) and str(r)[2] >= cutoff_str
        ]

        with open("data.json", "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

        return jsonify({"status": "success"})

    except Exception as e:
        print(f"Error in not_rasp_player: {e}")
        return jsonify({"status": "error", "msg": "Internal error"}), 500


@app.route("/student/<int:group_id>", methods=["GET"])
def send_stud(group_id: int):
    con = sqlite3.connect("students.db")
    data = con.execute(
        """
        SELECT id, vector
        FROM student
        WHERE id_group = ?
""",
        [group_id],
    ).fetchall()
    data = list(
        map(lambda x: [x[0], list(np.frombuffer(x[1], dtype=np.float64))], data)
    )
    return jsonify(data)


@app.route("/students", methods=["GET"])
def send_students():
    con = sqlite3.connect("students.db")
    data = con.execute(
        """
        SELECT *
        FROM student
"""
    ).fetchall()

    return jsonify(data)


@app.route("/rasp_group", methods=["GET"])
def send_rasp_group():
    con = sqlite3.connect("students.db")
    data = con.execute(
        """
        SELECT *
        FROM groups
"""
    ).fetchall()
    data = list(map(lambda x: (x[0], x[1], json.loads(x[2])), data))
    return jsonify(data)


@app.route("/sp_anti_app/<name>", methods=["GET"])
def send_sp_anti_app(name):
    con = sqlite3.connect("protiv.db")
    data = con.execute(
        """SELECT id FROM classroom WHERE INSTR(?, name) > 0""", [name]
    ).fetchall()
    id = []
    for i in data:
        id += con.execute(
            """SELECT id FROM filter WHERE classroom_id = ? AND activate = 1""", [i[0]]
        ).fetchall()
    sp_anti_app = []
    for i in id:
        sp_anti_app += con.execute(
            """SELECT name_app FROM anti_app WHERE block = 0 AND id_filter = ?""",
            [i[0]],
        ).fetchall()
    sp_anti_app = list(map(lambda x: x[0], sp_anti_app))
    return jsonify(sp_anti_app)


@app.route("/sp_anti_website/<name>", methods=["GET"])
def send_sp_anti_website(name):
    con = sqlite3.connect("protiv.db")
    data = con.execute(
        """SELECT id FROM classroom WHERE INSTR(?, name) > 0""", [name]
    ).fetchall()
    id = []
    for i in data:
        id += con.execute(
            """SELECT id FROM filter WHERE classroom_id = ? AND activate = 1""", [i[0]]
        ).fetchall()
    sp_anti_website = []
    for i in id:
        sp_anti_website += con.execute(
            """SELECT name_site FROM anti_website WHERE block = 0 AND id_filter = ?""",
            [i[0]],
        ).fetchall()
    sp_anti_website = list(map(lambda x: x[0], sp_anti_website))
    return jsonify(sp_anti_website)


@app.route("/protiv/app/<int:item_id>", methods=["DELETE"])
def delete_app(item_id):
    con = sqlite3.connect("protiv.db")
    con.execute("DELETE FROM anti_app WHERE id = ?", (item_id,))
    con.commit()
    return jsonify({"success": True})


@app.route("/protiv/website/<int:item_id>", methods=["DELETE"])
def delete_website(item_id):

    con = sqlite3.connect("protiv.db")
    con.execute("DELETE FROM anti_website WHERE id = ?", (item_id,))
    con.commit()
    return jsonify({"success": True})


@app.route("/who_played/<path>/<name_anti>", methods=["GET"])
def who_played(path, name_anti):
    con = sqlite3.connect("students.db")
    dat = con.execute(
        """SELECT id FROM pris WHERE student_id = ? AND data = ?""",
        [path, datetime.date.today().strftime("%Y-%m-%d")],
    ).fetchone()[0]
    con.execute(
        """INSERT INTO narush(anti_name,id_student,time,id_pris) VALUES(?,?,?,?)""",
        [
            name_anti,
            path,
            str(datetime.datetime.now()).split()[-1].split(":")[0]
            + ":"
            + str(datetime.datetime.now()).split()[-1].split(":")[1],
            dat,
        ],
    )
    con.commit()
    data = con.execute(
        """
    SELECT name_student
    FROM student
    WHERE id = ?
""",
        [path],
    ).fetchone()
    return jsonify(data)


@app.route("/add-group", methods=["GET", "POST"])  # type: ignore
def add_group():
    if request.method == "GET":
        if not is_logged_in():
            return redirect(url_for("login"))
        return render_template("add_group.html")
    elif request.method == "POST":
        group_name = request.form["group_name"]
        schedule = json.loads(request.form["schedule"])
        dict_rasp = {}
        for i in schedule:
            dict_rasp.update({str(sp.index(i["day"])): f"{i['start']}-{i['end']}"})
        con = sqlite3.connect("students.db")
        con.execute(
            """
            INSERT INTO groups(groups_name,rasp) 
            VALUES (?,?)
        """,
            [group_name, f"{dict_rasp}".replace("'", '"')],
        )
        con.commit()
        return redirect("/groups")


@app.route("/groups")
def index():
    if not is_logged_in():
        return redirect(url_for("login"))
    con = sqlite3.connect("students.db")
    a = con.execute(
        """
    SELECT *
    FROM groups
"""
    ).fetchall()
    return render_template(
        "index.html", groups=a, admin=session.get("is_admin") is not None
    )


@app.route("/schedule/<int:group_id>")
def group_rasp(group_id):
    if not is_logged_in():
        return redirect(url_for("login"))
    con = sqlite3.connect("students.db")
    data = con.execute(
        """
        SELECT *
        FROM groups
        WHERE id = ?
""",
        [group_id],
    ).fetchone()

    group_name = data[1]
    schedule_dict = json.loads(data[2])
    return render_template(
        "rasp_group.html",
        group_name=group_name,
        id_group=group_id,
        schedule_dict=schedule_dict,
    )


@app.route("/")
def glav():
    if not is_logged_in():
        return redirect(url_for("login"))
    return render_template("glav.html", admin=session.get("is_admin") is not None)


@app.route("/update_schedule/<int:id_group>", methods=["POST"])
def update_schedule(id_group):
    if not is_logged_in():
        return redirect(url_for("login"))
    schedule = {}
    days = ["0", "1", "2", "3", "4", "5", "6"]
    for day in days:
        time = request.form.get(f"time_{day}")
        if time and time.strip():
            schedule[day] = time.strip()
    con = sqlite3.connect("students.db")
    con.execute(
        """
    UPDATE groups
    SET rasp = ?
    WHERE id = ?
""",
        [f"{schedule}".replace("'", '"'), id_group],
    )
    con.commit()
    con.close()
    return redirect(f"/schedule/{id_group}")


@app.route("/add-block/<int:filter_id>", methods=["GET", "POST"])  # type: ignore
def show_add_form(filter_id):
    if request.method == "GET":
        if not is_logged_in():
            return redirect(url_for("login"))
        return render_template("add_block.html", filter_id=filter_id)
    elif request.method == "POST":
        name = request.form["name"].strip()
        block_type = request.form["type"]

        if not name:
            return "Имя не может быть пустым", 400
        con = sqlite3.connect("protiv.db")
        if block_type == "app":
            con.execute(
                "INSERT INTO anti_app (name_app, block,id_filter) VALUES (?, 0,?)",
                (name, filter_id),
            )
        elif block_type == "website":
            con.execute(
                "INSERT INTO anti_website (name_site, block,id_filter) VALUES (?, 0,?)",
                (name, filter_id),
            )

        con.commit()

        return redirect(f"/protiv/{filter_id}")


@app.route("/add_student/<int:id_group>", methods=["GET", "POST"])
def add_student(id_group):
    if request.method == "POST":
        name = str(request.form.get("student_name")).strip()
        photo = request.files.get("photo")

        if not name:
            return "Имя студента обязательно", 400

        filename = None
        if photo and photo.filename:
            if allowed_file(photo.filename):
                ext = photo.filename.rsplit(".", 1)[1].lower()
                filename = f"default.{ext}"
                photo.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            else:
                return "Недопустимый формат файла", 400
        else:
            return "Нужна фотография студента", 400

        img = io.imread(app.config["UPLOAD_FOLDER"] + "/" + filename)
        dets = detector(img, 1)
        try:
            for k, d in enumerate(dets):
                shape = model(img, d)
            face1 = facerec.compute_face_descriptor(img, shape)  # type: ignore
        except:
            return "Нужна фотография студента", 400
        embedding = np.array(face1).tobytes()
        con = sqlite3.connect("students.db")
        con.execute(
            "INSERT INTO student (name_student, vector, id_group) VALUES (?,?,?)",
            [name, embedding, id_group],
        )
        con.commit()

        return redirect(f"/group/{id_group}")
    if not is_logged_in():
        return redirect(url_for("login"))
    return render_template("add_student.html", id_group=id_group)


@app.route("/group/<int:id_group>")
def pris(id_group):
    if not is_logged_in():
        return redirect(url_for("login"))

    con = sqlite3.connect("students.db")
    cursor = con.cursor()

    group_name = cursor.execute(
        "SELECT groups_name FROM groups WHERE id = ?", (id_group,)
    ).fetchone()
    if not group_name:
        return "Группа не найдена", 404

    data_rows = cursor.execute(
        "SELECT DISTINCT data FROM pris WHERE group_id = ?", (id_group,)
    ).fetchall()
    dates = sorted([row[0] for row in data_rows])

    students = cursor.execute(
        "SELECT id, name_student FROM student WHERE id_group = ?", (id_group,)
    ).fetchall()

    pris_rows = cursor.execute(
        "SELECT student_id, data FROM pris WHERE group_id = ?", (id_group,)
    ).fetchall()
    attendance = set(pris_rows)

    violations_dict = {}
    violations_rows = cursor.execute(
        """
        SELECT n.anti_name, n.id_student, n.time, p.data
        FROM narush n
        JOIN pris p ON n.id_pris = p.id
        WHERE p.group_id = ?
        """,
        (id_group,),
    ).fetchall()

    for anti_name, student_id, time, date_val in violations_rows:
        key = (student_id, date_val)
        if key not in violations_dict:
            violations_dict[key] = []
        violations_dict[key].append({"time": time, "description": anti_name})

    con.close()

    try:
        with open("data.json", encoding="utf-8") as f:
            all_unrecognized = json.load(f)
        all_unrecognized = list(all_unrecognized)
        res = []
        cutoff = datetime.date.today() - datetime.timedelta(days=7)
        cutoff_str = cutoff.strftime("%Y-%m-%d")
        for i in all_unrecognized:
            if i[2] >= cutoff_str:
                res.append(i)
        with open("data.json", encoding="utf-8", mode="w") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
    except (FileNotFoundError, json.JSONDecodeError, ValueError, IndexError):
        pass

    dates = sorted(dates)
    res = sorted(res, key=lambda x: x[3], reverse=True)[:3]  # type: ignore
    return render_template(
        "table_pris.html",
        group_name=group_name[0],
        dates=dates,
        students=students,
        attendance=attendance,
        violations=violations_dict,
        unrecognized_today=res,
        id_group=id_group,
        admin=session.get("is_admin") is not None,
    )


@app.route("/unrecognized_today")
def unrecognized_today_api():
    today = datetime.date.today().strftime("%Y-%m-%d")
    try:
        with open("data.json", encoding="utf-8") as f:
            all_unrecognized = json.load(f)
        all_unrecognized = list(all_unrecognized)
        res = []
        cutoff = datetime.date.today() - datetime.timedelta(days=7)
        cutoff_str = cutoff.strftime("%Y-%m-%d")
        for i in all_unrecognized:
            if i[2] >= cutoff_str:
                res.append(i)
        with open("data.json", encoding="utf-8", mode="w") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
    except (FileNotFoundError, json.JSONDecodeError, ValueError, IndexError):
        pass
    return jsonify(res)  # type: ignore


@app.route("/delete_student/<int:student_id>", methods=["POST"])
def delete_student(student_id):
    con = sqlite3.connect("students.db")
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("""DELETE FROM student WHERE id = ?""", [student_id])
    con.commit()
    return redirect("/groups")


@app.route("/delete_group/<int:id_group>", methods=["POST"])
def delete_group(id_group):
    con = sqlite3.connect("students.db")
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("""DELETE FROM groups WHERE id = ?""", [id_group])
    con.commit()
    return redirect("/groups")


@app.route("/classrooms", methods=["GET"])
def classrooms():
    if not is_logged_in():
        return redirect(url_for("login"))
    con = sqlite3.connect("protiv.db")
    data = con.execute("""SELECT * FROM classroom""")
    return render_template("classrooms.html", classrooms=data)


@app.route("/delete_classroom/<int:id>", methods=["GET"])
def delete_classroom(id):
    if not is_logged_in():
        return redirect(url_for("login"))
    con = sqlite3.connect("protiv.db")
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("""DELETE FROM classroom WHERE id = ?""", [id])
    con.commit()
    return redirect("/classrooms")


@app.route("/new_classroom", methods=["GET", "POST"])
def new_classroom():
    if request.method == "GET":
        if not is_logged_in():
            return redirect(url_for("login"))
        return render_template("add_classroom.html")
    else:
        name = request.form["name"]
        con = sqlite3.connect("protiv.db")
        con.execute("""INSERT INTO classroom (name) VALUES (?)""", [name])
        con.commit()
        data = con.execute("""SELECT id FROM classroom""").fetchall()
        return redirect(f"/filter/{data[-1][0]}")


@app.route("/filter/<int:classroom_id>", methods=["GET"])
def filters(classroom_id):
    if not is_logged_in():
        return redirect(url_for("login"))
    con = sqlite3.connect("protiv.db")
    data = con.execute(
        """SELECT * FROM filter WHERE classroom_id = ?""", [classroom_id]
    ).fetchall()
    name = con.execute(
        """SELECT name FROM classroom WHERE id = ?""", [classroom_id]
    ).fetchone()[0]
    print(data, name)
    return render_template("filters.html", data=data, name=name, id=classroom_id)


@app.route("/update-filter-status", methods=["POST"])
def update_filter_status():
    data = request.get_json()
    filter_id = data.get("id")
    is_active = data.get("is_active")
    con = sqlite3.connect("protiv.db")
    con.execute(
        """ UPDATE filter SET activate = ? WHERE id = ?""", [is_active, filter_id]
    )
    con.commit()
    return jsonify({"success": True})


@app.route("/delete-filter/<int:filter_id>", methods=["DELETE"])
def delete_filter(filter_id):
    con = sqlite3.connect("protiv.db")
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("DELETE FROM filter WHERE id = ?", [filter_id])
    con.commit()
    return jsonify({"success": True})


@app.route("/new_filter/<int:classroom_id>", methods=["GET", "POST"])
def new_filter(classroom_id):
    if request.method == "GET":
        if not is_logged_in():
            return redirect(url_for("login"))
        return render_template("add_filter.html", id=classroom_id)
    else:
        data = request.form["filterName"]
        con = sqlite3.connect("protiv.db")
        con.execute(
            """INSERT INTO filter(name_filter, classroom_id, activate) VALUES (?,?,0)""",
            [data, classroom_id],
        )
        con.commit()
        return redirect(f"/filter/{classroom_id}")


@app.route("/protiv/<filter_id>", methods=["GET", "POST"])  # type: ignore
def protiv(filter_id):
    if request.method == "GET":
        if not is_logged_in():
            return redirect(url_for("login"))
        con = sqlite3.connect("protiv.db")
        anti_app = con.execute(
            """
        SELECT *
        FROM anti_app
        WHERE id_filter = ?
    """,
            [filter_id],
        )
        anti_website = con.execute(
            """
        SELECT *
        FROM anti_website
        WHERE id_filter = ?
    """,
            [filter_id],
        )
        data = con.execute(
            """SELECT name_filter FROM filter WHERE id = ?""", [filter_id]
        ).fetchone()[0]
        return render_template(
            "protiv.html",
            anti_app=anti_app,
            anti_website=anti_website,
            name=data,
            id=filter_id,
        )
    elif request.method == "POST":
        data = request.get_json()
        con = sqlite3.connect("protiv.db")
        for app in data.get("anti_app", []):
            app_id = app["id"]
            state = app["state"]
            con.execute(
                """
            UPDATE anti_app
            SET block = ?
            WHERE id = ?
            """,
                [state, app_id],
            )

        for website in data.get("anti_website", []):
            site_id = website["id"]
            state = website["state"]
            con.execute(
                """
            UPDATE anti_website
            SET block = ?
            WHERE id = ?
            """,
                [state, site_id],
            )
        con.commit()
        return jsonify({"message": "Настройки успешно сохранены!"})


@app.route("/latest_violations/<int:group_id>")
def latest_violations(group_id):
    con = sqlite3.connect("students.db")
    data = con.execute(
        """
        SELECT student.name_student, narush.time, narush.anti_name 
        FROM narush INNER JOIN student ON narush.id_student = student.id 
        WHERE narush.group_id = ?
        """,
        [group_id],
    ).fetchall()[-3:][::-1]

    return jsonify(data)


@app.route("/teachers", methods=["GET", "POST"])
def teachears():
    if not is_logged_in():
        return redirect(url_for("login"))
    con = sqlite3.connect("teachers.db")
    sp = con.execute("""SELECT id,name_teacher FROM teachers""").fetchall()
    con.close()
    print(sp)
    return render_template("teachers.html", teachers=sp)


@app.route("/teacher/delete/<int:teacher_id>", methods=["POST"])
def delete_teacher(teacher_id):
    con = sqlite3.connect("teachers.db")
    con.execute("""DELETE FROM teachers WHERE id = ?""", [teacher_id])
    con.commit()
    return redirect(url_for("teachears"))


@app.route("/add_teachers", methods=["GET", "POST"])
def add_teach():
    if not is_logged_in():
        return redirect(url_for("login"))
    if request.method == "POST":
        name = request.form["full_name"]
        login = request.form["login"]
        password = request.form["password"]
        con = sqlite3.connect("teachers.db")
        con.execute(
            """INSERT INTO teachers (login, password, name_teacher) VALUES (?, ?, ?)""",
            [login, hash_func(password), name],
        )
        con.commit()
        con.close()
        return redirect(url_for("glav"))
    return render_template("add_teachers.html")


@app.route("/assign_session", methods=["POST"])
def assign_session():
    data = request.get_json()
    id_komp = int(data.get("record_id"))
    student_id = data.get("student_id")
    with open("data.json", encoding="UTF-8") as file:
        sp = list(json.load(file))
    sp1 = list(map(lambda x: x[0], sp))
    s = sp[sp1.index(id_komp)]
    sp.pop(sp1.index(id_komp))
    print(sp)
    con = sqlite3.connect("students.db")
    id_pris = con.execute(
        """SELECT id FROM pris WHERE student_id = ? AND data = ?""", [student_id, s[3]]
    ).fetchone()
    if id_pris is not None:
        id_pris = id_pris[0]
    else:
        return jsonify({"error": "Студент не присутсутвовал в тот день"}), 400
    with open("data.json", mode="w", encoding="UTF-8") as file:
        json.dump(sp, file)
    group_id = con.execute(
        """SELECT id_group FROM student WHERE id = ?""", [student_id]
    ).fetchone()[0]
    con.execute(
        """INSERT INTO narush (anti_name, id_student, time, id_pris, group_id) VALUES (?, ?, ?, ?, ?)""",
        [s[1], student_id, s[4], id_pris, group_id],
    )
    con.commit()
    return jsonify({"status": "ok", "id_komp": id_komp, "student_id": student_id})


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        con = sqlite3.connect("teachers.db")
        data = con.execute(
            """SELECT * FROM teachers WHERE login = ? AND password = ?""",
            [username, hash_func(password)],
        ).fetchone()
        con.close()

        if (
            hash_func(username) == ADMIN_CREDENTIALS["username"]
            and hash_func(password) == ADMIN_CREDENTIALS["password"]
        ):
            session["is_login"] = True
            session["is_admin"] = True

            flash("Добро пожаловать, админ!", "success")
            return redirect(url_for("glav"))
        elif data is not None:
            session["is_login"] = True
            flash(f"Добро пожаловать, {data[-1]}!", "success")
            return redirect(url_for("glav"))
        else:
            flash("Неверный логин или пароль.", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Вы вышли из системы.", "info")
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
