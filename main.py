import datetime
import os
import json
import hashlib
import io
import numpy as np
import face_recognition
from skimage import io as ios

from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException, Depends, status
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from sqlalchemy import select, update, delete, func, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from init_db import (
    DATABASE_URL, Base, Group, Student, Pris, Classroom, 
    Filter, AntiWebsite, AntiApp, Narush, Teacher
)

app = FastAPI()

# Добавляем middleware для сессий
app.add_middleware(SessionMiddleware, secret_key=b'_5#y2L"F4Q8z\n\xec]/')

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

UPLOAD_FOLDER = "static/photos"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ADMIN_CREDENTIALS = {
    "username": "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918",
    "password": "44ac9a7d1fed334c2d41c75d56e33e04857988f767ae4fccac6b6b1799dd8f80",
}

sp_days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]

# Создание асинхронного движка и фабрики сессий
engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# Зависимость для сессий базы данных
async def get_db():
    async with async_session() as session:
        async with session.begin():
            await session.execute(text("PRAGMA foreign_keys = ON;"))
            yield session

def hash_func(s: str):
    return hashlib.sha256(s.encode()).hexdigest()

def allowed_file(filename: str):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def is_logged_in(request: Request):
    return request.session.get("is_login") is True


@app.post("/upload")
async def upload_data(request: Request, db: AsyncSession = Depends(get_db)):
    data = await request.json()
    result = await db.execute(select(Student.id_group).where(Student.id == int(data)))
    group_id = result.scalar_one_or_none()
    
    if not group_id:
        raise HTTPException(status_code=404, detail="Студент не найден")
    
    new_pris = Pris(
        group_id=group_id,
        student_id=int(data),
        data=datetime.date.today().strftime("%Y-%m-%d")
    )
    db.add(new_pris)
    return {"status": "success"}


@app.post("/not_rasp_player")
async def not_rasp_player(request: Request):
    try:
        data = await request.json()
        if not isinstance(data, list) or len(data) < 2:
            return JSONResponse({"status": "error", "msg": "Expected list with at least 2 elements"}, status_code=400)

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

        if not records:
            records = [[0]]

        new_record = [max(map(lambda x: x[0], records)) + 1] + new_record
        records.append(new_record)

        cutoff = datetime.date.today() - datetime.timedelta(days=7)
        cutoff_str = cutoff.strftime("%Y-%m-%d")
        records = [r for r in records if len(r) >= 4 and isinstance(r[2], str) and r[2] >= cutoff_str]

        with open("data.json", "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

        return {"status": "success"}
    except Exception as e:
        print(f"Error in not_rasp_player: {e}")
        return JSONResponse({"status": "error", "msg": "Internal error"}, status_code=500)


@app.get("/student/{group_id}")
async def send_stud(group_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Student.id, Student.vector).where(Student.id_group == group_id))
    students = result.all()
    
    data = []
    for s_id, vector in students:
        if vector:
            vec_list = list(np.frombuffer(vector, dtype=np.float64))
        else:
            vec_list = []
        data.append([s_id, vec_list])
    return data


@app.get("/students")
async def send_students(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Student))
    students = result.scalars().all()
    return [{"id": s.id, "name_student": s.name_student, "id_group": s.id_group} for s in students]


@app.get("/rasp_group")
async def send_rasp_group(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Group))
    groups = result.scalars().all()
    
    data = []
    for g in groups:
        rasp_obj = json.loads(g.rasp) if g.rasp else {}
        data.append((g.id, g.groups_name, rasp_obj))
    return data


@app.get("/sp_anti_app/{name}")
async def send_sp_anti_app(name: str, db: AsyncSession = Depends(get_db)):
    classrooms_res = await db.execute(select(Classroom.id).where(func.instr(name, Classroom.name) > 0))
    classroom_ids = classrooms_res.scalars().all()

    if not classroom_ids:
        return []

    filters_res = await db.execute(
        select(Filter.id).where(Filter.classroom_id.in_(classroom_ids), Filter.activate == 1)
    )
    filter_ids = filters_res.scalars().all()

    if not filter_ids:
        return []

    apps_res = await db.execute(
        select(AntiApp.name_app).where(AntiApp.block == 0, AntiApp.id_filter.in_(filter_ids))
    )
    return apps_res.scalars().all()


@app.get("/sp_anti_website/{name}")
async def send_sp_anti_website(name: str, db: AsyncSession = Depends(get_db)):
    classrooms_res = await db.execute(select(Classroom.id).where(func.instr(name, Classroom.name) > 0))
    classroom_ids = classrooms_res.scalars().all()

    if not classroom_ids:
        return []

    filters_res = await db.execute(
        select(Filter.id).where(Filter.classroom_id.in_(classroom_ids), Filter.activate == 1)
    )
    filter_ids = filters_res.scalars().all()

    if not filter_ids:
        return []

    sites_res = await db.execute(
        select(AntiWebsite.name_site).where(AntiWebsite.block == 0, AntiWebsite.id_filter.in_(filter_ids))
    )
    return sites_res.scalars().all()


@app.delete("/protiv/app/{item_id}")
async def delete_app(item_id: int, db: AsyncSession = Depends(get_db)):
    await db.execute(delete(AntiApp).where(AntiApp.id == item_id))
    return {"success": True}


@app.delete("/protiv/website/{item_id}")
async def delete_website(item_id: int, db: AsyncSession = Depends(get_db)):
    await db.execute(delete(AntiWebsite).where(AntiWebsite.id == item_id))
    return {"success": True}


@app.get("/who_played/{path}/{name_anti}")
async def who_played(path: int, name_anti: str, db: AsyncSession = Depends(get_db)):
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    pris_res = await db.execute(select(Pris.id).where(Pris.student_id == path, Pris.data == today_str))
    pris_id = pris_res.scalar_one_or_none()

    now_time = datetime.datetime.now().strftime("%H:%M")

    new_narush = Narush(
        anti_name=name_anti,
        id_student=path,
        time=now_time,
        id_pris=pris_id
    )
    db.add(new_narush)

    student_res = await db.execute(select(Student.name_student).where(Student.id == path))
    student_name = student_res.scalar_one_or_none()

    return [student_name] if student_name else []


@app.get("/add-group")
async def add_group_get(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request, "add_group.html")


@app.post("/add-group")
async def add_group_post(request: Request, group_name: str = Form(...), schedule: str = Form(...), db: AsyncSession = Depends(get_db)):
    sched_list = json.loads(schedule)
    dict_rasp = {}
    for i in sched_list:
        dict_rasp.update({str(sp_days.index(i["day"])): f"{i['start']}-{i['end']}"})

    new_group = Group(groups_name=group_name, rasp=json.dumps(dict_rasp))
    db.add(new_group)
    return RedirectResponse(url="/groups", status_code=303)


@app.get("/groups")
async def index_groups(request: Request, db: AsyncSession = Depends(get_db)):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)
    
    result = await db.execute(select(Group))
    groups = result.scalars().all()
    return templates.TemplateResponse(request, "index.html", {
        "groups": groups, 
        "admin": request.session.get("is_admin") is not None
    })


@app.get("/schedule/{group_id}")
async def group_rasp(group_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)
    
    result = await db.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    schedule_dict = json.loads(group.rasp) if group.rasp else {}
    return templates.TemplateResponse(request, "rasp_group.html", {
        "group_name": group.groups_name,
        "id_group": group_id,
        "schedule_dict": schedule_dict,
    })


@app.get("/")
async def glav(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request, "glav.html", {
        "admin": request.session.get("is_admin") is not None
    })


@app.post("/update_schedule/{id_group}")
async def update_schedule(id_group: int, request: Request, db: AsyncSession = Depends(get_db)):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)

    form_data = await request.form()
    schedule = {}
    for day in ["0", "1", "2", "3", "4", "5", "6"]:
        t = form_data.get(f"time_{day}")
        if t and str(t).strip():
            schedule[day] = str(t).strip()

    await db.execute(
        update(Group).where(Group.id == id_group).values(rasp=json.dumps(schedule))
    )
    return RedirectResponse(url=f"/schedule/{id_group}", status_code=303)


@app.get("/add-block/{filter_id}")
async def show_add_form_get(filter_id: int, request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request, "add_block.html", {"filter_id": filter_id})


@app.post("/add-block/{filter_id}")
async def show_add_form_post(
    filter_id: int, 
    request: Request, 
    name: str = Form(...), 
    type: str = Form(...), 
    db: AsyncSession = Depends(get_db)
):
    name_clean = name.strip()
    if not name_clean:
        raise HTTPException(status_code=400, detail="Имя не может быть пустым")

    if type == "app":
        new_item = AntiApp(name_app=name_clean, block=0, id_filter=filter_id)
        db.add(new_item)
    elif type == "website":
        new_item = AntiWebsite(name_site=name_clean, block=0, id_filter=filter_id)
        db.add(new_item)

    return RedirectResponse(url=f"/protiv/{filter_id}", status_code=303)


@app.get("/add_student/{id_group}")
async def add_student_get(id_group: int, request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request, "add_student.html", {"id_group": id_group})


@app.post("/add_student/{id_group}")
async def add_student_post(
    id_group: int, 
    student_name: str = Form(...), 
    photo: UploadFile = File(...), 
    db: AsyncSession = Depends(get_db)
):
    name = student_name.strip()
    if not name or not photo.filename or not allowed_file(photo.filename):
        raise HTTPException(status_code=400, detail="Недопустимые параметры или расширение файла")

    photo_bytes = await photo.read()
    if not photo_bytes:
        raise HTTPException(status_code=400, detail="Файл пустой")

    try:
        img = ios.imread(io.BytesIO(photo_bytes))
        face_encodings = face_recognition.face_encodings(img)
        if len(face_encodings) == 0:
            raise HTTPException(status_code=400, detail="Лицо не найдено на фотографии")
        embedding = face_encodings[0].tobytes()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ошибка обработки изображения: {str(e)}")

    new_student = Student(name_student=name, vector=embedding, id_group=id_group)
    db.add(new_student)

    return {"success": True}


@app.get("/group/{id_group}")
async def pris_view(id_group: int, request: Request, db: AsyncSession = Depends(get_db)):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)

    group_res = await db.execute(select(Group.groups_name).where(Group.id == id_group))
    group_name = group_res.scalar_one_or_none()
    if not group_name:
        raise HTTPException(status_code=404, detail="Группа не найдена")

    dates_res = await db.execute(select(Pris.data).where(Pris.group_id == id_group).distinct())
    dates = sorted([d for d in dates_res.scalars().all() if d])

    students_res = await db.execute(select(Student.id, Student.name_student).where(Student.id_group == id_group))
    students = students_res.all()

    pris_res = await db.execute(select(Pris.student_id, Pris.data).where(Pris.group_id == id_group))
    attendance = set(pris_res.all())

    violations_res = await db.execute(
        select(Narush.anti_name, Narush.id_student, Narush.time, Pris.data)
        .join(Pris, Narush.id_pris == Pris.id)
        .where(Pris.group_id == id_group)
    )

    violations_dict = {}
    for anti_name, student_id, v_time, date_val in violations_res.all():
        key = (student_id, date_val)
        if key not in violations_dict:
            violations_dict[key] = []
        violations_dict[key].append({"time": v_time, "description": anti_name})

    res = []
    try:
        with open("data.json", encoding="utf-8") as f:
            all_unrecognized = json.load(f)
        cutoff_str = (datetime.date.today() - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
        res = [i for i in all_unrecognized if len(i) >= 3 and i[2] >= cutoff_str]
        with open("data.json", encoding="utf-8", mode="w") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    res = sorted(res, key=lambda x: x[3], reverse=True)[:3]
    return templates.TemplateResponse(request, "table_pris.html", {
        "group_name": group_name,
        "dates": dates,
        "students": students,
        "attendance": attendance,
        "violations": violations_dict,
        "unrecognized_today": res,
        "id_group": id_group,
        "admin": request.session.get("is_admin") is not None,
    })


@app.get("/unrecognized_today")
async def unrecognized_today_api():
    res = []
    try:
        with open("data.json", encoding="utf-8") as f:
            all_unrecognized = json.load(f)
        cutoff_str = (datetime.date.today() - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
        res = [i for i in all_unrecognized if len(i) >= 3 and i[2] >= cutoff_str]
        with open("data.json", encoding="utf-8", mode="w") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return res


@app.post("/delete_student/{student_id}")
async def delete_student(student_id: int, db: AsyncSession = Depends(get_db)):
    await db.execute(delete(Student).where(Student.id == student_id))
    return RedirectResponse(url="/groups", status_code=303)


@app.post("/delete_group/{id_group}")
async def delete_group(id_group: int, db: AsyncSession = Depends(get_db)):
    await db.execute(delete(Group).where(Group.id == id_group))
    return RedirectResponse(url="/groups", status_code=303)


@app.get("/classrooms")
async def classrooms(request: Request, db: AsyncSession = Depends(get_db)):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)
    res = await db.execute(select(Classroom))
    classrooms_list = res.scalars().all()
    return templates.TemplateResponse(request, "classrooms.html", {"classrooms": classrooms_list})


@app.get("/delete_classroom/{id}")
async def delete_classroom(id: int, request: Request, db: AsyncSession = Depends(get_db)):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)
    await db.execute(delete(Classroom).where(Classroom.id == id))
    return RedirectResponse(url="/classrooms", status_code=303)


@app.get("/new_classroom")
async def new_classroom_get(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request, "add_classroom.html")


@app.post("/new_classroom")
async def new_classroom_post(name: str = Form(...), db: AsyncSession = Depends(get_db)):
    new_room = Classroom(name=name)
    db.add(new_room)
    await db.flush()  # Для получения сгенерированного ID
    return RedirectResponse(url=f"/filter/{new_room.id}", status_code=303)


@app.get("/filter/{classroom_id}")
async def filters(classroom_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)

    filters_res = await db.execute(select(Filter).where(Filter.classroom_id == classroom_id))
    filter_data = filters_res.scalars().all()

    room_res = await db.execute(select(Classroom.name).where(Classroom.id == classroom_id))
    room_name = room_res.scalar_one_or_none()

    return templates.TemplateResponse(request, "filters.html", {
        "data": filter_data, 
        "name": room_name, 
        "id": classroom_id
    })


@app.post("/update-filter-status")
async def update_filter_status(request: Request, db: AsyncSession = Depends(get_db)):
    data = await request.json()
    filter_id = data.get("id")
    is_active = data.get("is_active")

    await db.execute(
        update(Filter).where(Filter.id == filter_id).values(activate=is_active)
    )
    return {"success": True}


@app.delete("/delete-filter/{filter_id}")
async def delete_filter(filter_id: int, db: AsyncSession = Depends(get_db)):
    await db.execute(delete(Filter).where(Filter.id == filter_id))
    return {"success": True}


@app.get("/new_filter/{classroom_id}")
async def new_filter_get(classroom_id: int, request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request, "add_filter.html", {"id": classroom_id})


@app.post("/new_filter/{classroom_id}")
async def new_filter_post(classroom_id: int, filterName: str = Form(...), db: AsyncSession = Depends(get_db)):
    new_f = Filter(name_filter=filterName, classroom_id=classroom_id, activate=0)
    db.add(new_f)
    return RedirectResponse(url=f"/filter/{classroom_id}", status_code=303)


@app.get("/protiv/{filter_id}")
async def protiv_get(filter_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)

    apps_res = await db.execute(select(AntiApp).where(AntiApp.id_filter == filter_id))
    sites_res = await db.execute(select(AntiWebsite).where(AntiWebsite.id_filter == filter_id))
    f_res = await db.execute(select(Filter.name_filter).where(Filter.id == filter_id))

    return templates.TemplateResponse(request, "protiv.html", {
        "anti_app": apps_res.scalars().all(),
        "anti_website": sites_res.scalars().all(),
        "name": f_res.scalar_one_or_none(),
        "id": filter_id,
    })


@app.post("/protiv/{filter_id}")
async def protiv_post(filter_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    data = await request.json()
    
    for app_item in data.get("anti_app", []):
        await db.execute(
            update(AntiApp).where(AntiApp.id == app_item["id"]).values(block=app_item["state"])
        )

    for site_item in data.get("anti_website", []):
        await db.execute(
            update(AntiWebsite).where(AntiWebsite.id == site_item["id"]).values(block=site_item["state"])
        )

    return {"message": "Настройки успешно сохранены!"}


@app.get("/latest_violations/{group_id}")
async def latest_violations(group_id: int, db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(Student.name_student, Narush.time, Narush.anti_name)
        .join(Student, Narush.id_student == Student.id)
        .where(Narush.group_id == group_id)
    )
    rows = res.all()
    data = [[r[0], r[1], r[2]] for r in rows[-3:][::-1]]
    return data


@app.get("/teachers")
async def teachers_view(request: Request, db: AsyncSession = Depends(get_db)):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)

    res = await db.execute(select(Teacher.id, Teacher.name_teacher))
    return templates.TemplateResponse(request, "teachers.html", {"teachers": res.all()})


@app.post("/teacher/delete/{teacher_id}")
async def delete_teacher(teacher_id: int, db: AsyncSession = Depends(get_db)):
    await db.execute(delete(Teacher).where(Teacher.id == teacher_id))
    return RedirectResponse(url="/teachers", status_code=303)


@app.get("/add_teachers")
async def add_teach_get(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request, "add_teachers.html")


@app.post("/add_teachers")
async def add_teach_post(
    request: Request, 
    full_name: str = Form(...), 
    login: str = Form(...), 
    password: str = Form(...), 
    db: AsyncSession = Depends(get_db)
):
    new_teacher = Teacher(
        login=login,
        password=hash_func(password),
        name_teacher=full_name
    )
    db.add(new_teacher)
    return RedirectResponse(url="/", status_code=303)


@app.post("/assign_session")
async def assign_session(request: Request, db: AsyncSession = Depends(get_db)):
    data = await request.json()
    id_komp = int(data.get("record_id"))
    student_id = data.get("student_id")

    with open("data.json", encoding="UTF-8") as file:
        sp = list(json.load(file))
    sp1 = list(map(lambda x: x[0], sp))
    
    if id_komp not in sp1:
        return JSONResponse({"error": "Запись не найдена в data.json"}, status_code=400)

    s = sp[sp1.index(id_komp)]
    sp.pop(sp1.index(id_komp))

    pris_res = await db.execute(select(Pris.id).where(Pris.student_id == student_id, Pris.data == s[3]))
    id_pris = pris_res.scalar_one_or_none()

    if id_pris is None:
        return JSONResponse({"error": "Студент не присутствовал в тот день"}, status_code=400)

    with open("data.json", mode="w", encoding="UTF-8") as file:
        json.dump(sp, file)

    st_res = await db.execute(select(Student.id_group).where(Student.id == student_id))
    group_id = st_res.scalar_one_or_none()

    new_narush = Narush(
        anti_name=s[1],
        id_student=student_id,
        time=s[4],
        id_pris=id_pris,
        group_id=group_id
    )
    db.add(new_narush)

    return {"status": "ok", "id_komp": id_komp, "student_id": student_id}


@app.get("/login")
async def login_get(request: Request):
    return templates.TemplateResponse(request, "login.html")


@app.post("/login")
async def login_post(
    request: Request, 
    username: str = Form(...), 
    password: str = Form(...), 
    db: AsyncSession = Depends(get_db)
):
    teacher_res = await db.execute(
        select(Teacher).where(Teacher.login == username, Teacher.password == hash_func(password))
    )
    teacher = teacher_res.scalar_one_or_none()

    if hash_func(username) == ADMIN_CREDENTIALS["username"] and hash_func(password) == ADMIN_CREDENTIALS["password"]:
        request.session["is_login"] = True
        request.session["is_admin"] = True
        return RedirectResponse(url="/", status_code=303)
    elif teacher is not None:
        request.session["is_login"] = True
        return RedirectResponse(url="/", status_code=303)
    else:
        return templates.TemplateResponse(request, "login.html", {"error": "Неверный логин или пароль"})


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)